// EXTRA.JS — read-only additional proofs for AUDIT.CMD using stock WinPE cscript.
// Requires only Microsoft Windows Script Host, FSO, MSXML6 and WMI.
// Arguments: target disk number, ESP letter, Windows letter, WinRE letter,
//            answer-media letter, TARGET-ONLY DiskPart log.
// Never executes a command, creates a file, writes a registry key or changes a disk.
(function () {
    if (WScript.Arguments.length !== 6) {
        WScript.Echo("FATAL bad arguments");
        WScript.Quit(2);
    }
    var disk = Number(WScript.Arguments(0));
    var esp = String(WScript.Arguments(1)).toUpperCase();
    var os = String(WScript.Arguments(2)).toUpperCase();
    var re = String(WScript.Arguments(3)).toUpperCase();
    var answer = String(WScript.Arguments(4)).toUpperCase();
    var diskpartLog = String(WScript.Arguments(5));
    var FSO = new ActiveXObject("Scripting.FileSystemObject");
    function verdict(id, state, explanation) {
        WScript.Echo("WSHCHECK " + id + " " + state + " " + explanation);
    }
    function fatal(id, err) {
        verdict(id, "FAIL", "exception_" + (err.message || err.description || err.number || "unknown"));
    }
    function xmlDoc(file) {
        var d = new ActiveXObject("Msxml2.DOMDocument.6.0");
        d.async = false;
        d.resolveExternals = false;
        d.validateOnParse = false;
        if (!d.load(file)) { throw new Error("Invalid_XML_" + d.parseError.errorCode); }
        return d;
    }
    function safeText(file) {
        var s = FSO.OpenTextFile(file, 1, false, 0);
        var text = s.ReadAll();
        s.Close();
        return text;
    }
    function readBytesExact(file, sz) {
        // For an ASCII XML every byte is one FSO TristateFalse character.
        // Check every code point, not just equal strings: ANSI code-page
        // conversion must NEVER turn different source bytes into PASS.
        // Works for odd AND even sizes, without MSXML serialization/normalization.
        var stream = FSO.OpenTextFile(file, 1, false, 0);
        var text = stream.ReadAll();
        stream.Close();
        if (text.length !== sz) throw new Error("ASCII_byte_count_mismatch");
        if (text.substr(0, 2) !== "<?") throw new Error("Unexpected_XML_preamble");
        for (var i = 0; i < text.length; i++) {
            if (text.charCodeAt(i) > 127) {
                throw new Error("Non_ASCII_XML_requires_binary_reader");
            }
        }
        return text;
    }
    var installed = os + ":\\Windows\\Panther\\Unattend.xml";
    var canonical = answer + ":\\Autounattend.xml";
    try {
        var ia = FSO.GetFile(installed), ib = FSO.GetFile(canonical);
        xmlDoc(installed); xmlDoc(canonical);
        if (ia.Size !== ib.Size) {
            verdict("windows.answer_identity", "FAIL", "XML_file_size_differs");
        } else {
            var lhs = readBytesExact(installed, ia.Size);
            var rhs = readBytesExact(canonical, ib.Size);
            verdict("windows.answer_identity", lhs === rhs ? "PASS" : "FAIL",
                    lhs === rhs ? "Exact_source_bytes_equal" : "XML_source_bytes_differ");
        }
    } catch (e) { fatal("windows.answer_identity", e); }

    // WMI Win32_DiskPartition reports precise byte sizes/offsets of visible
    // partitions. On this WinPE, MSR is deliberately omitted by Win32_...
    // but its exact 16 MiB gap is recoverable between ESP and Windows.
    var partitions = [], diskSize = -1, logical = {}, diskID = "";
    try {
        var svc = new ActiveXObject("WbemScripting.SWbemLocator").ConnectServer(".", "root\\cimv2");
        var drives = new Enumerator(svc.ExecQuery("select Index,Size from Win32_DiskDrive"));
        for (; !drives.atEnd(); drives.moveNext()) {
            var dev = drives.item();
            if (Number(dev.Index) === disk) diskSize = Number(dev.Size);
        }
        var pts = new Enumerator(svc.ExecQuery("select DiskIndex,Index,Size,StartingOffset,Type from Win32_DiskPartition"));
        for (; !pts.atEnd(); pts.moveNext()) {
            var part = pts.item();
            if (Number(part.DiskIndex) === disk) {
                partitions.push({index: Number(part.Index), size: Number(part.Size),
                                 offset: Number(part.StartingOffset), type: String(part.Type)});
            }
        }
        var assoc = new Enumerator(svc.ExecQuery("select Antecedent,Dependent from Win32_LogicalDiskToPartition"));
        for (; !assoc.atEnd(); assoc.moveNext()) {
            var row = assoc.item(), a = String(row.Antecedent), b = String(row.Dependent);
            var matchA = /Disk #(\d+), Partition #(\d+)/i.exec(a);
            var matchB = /DeviceID="([A-Z]:)"/i.exec(b);
            if (matchA && matchB && Number(matchA[1]) === disk) {
                logical[matchB[1].charAt(0).toUpperCase()] = Number(matchA[2]);
            }
        }
        partitions.sort(function (a, b) { return a.offset - b.offset; });
        // WMI often doesn't enumerate MSR. Find only the three mapped volumes.
        function get(letter) {
            var index = logical[letter];
            for (var i = 0; i < partitions.length; i++) {
                if (partitions[i].index === index) return partitions[i];
            }
            return null;
        }
        var pEsp = get(esp), pWin = get(os), pRe = get(re);
        var mapping = !!(pEsp && pWin && pRe && pEsp.index !== pWin.index &&
                         pWin.index !== pRe.index && pEsp.index !== pRe.index);
        verdict("target.physical_volume_mapping", mapping ? "PASS" : "FAIL",
                mapping ? "ESP_Windows_Recovery_volumes_match_target_disk" : "Volume_to_target_disk_mismatch");
        var MiB = 1048576;
        var exact = mapping &&
            pEsp.size === 300 * MiB && pRe.size === 2048 * MiB &&
            pEsp.offset + pEsp.size + 16 * MiB === pWin.offset &&
            pWin.offset + pWin.size === pRe.offset &&
            pRe.offset + pRe.size <= diskSize &&
            diskSize - (pRe.offset + pRe.size) <= 2 * MiB &&
            pWin.size > 2048 * MiB;
        // WMI starts at the first usable aligned LBA and the last partition
        // ends just before backup GPT. Up to 2MiB tail covers 512e and 4Kn.
        // Keep the exact strict acceptance predicate, but report which
        // byte-precise part actually failed. No changes to partition layout.
        var geometryFailures = [];
        if (!mapping) {
            geometryFailures.push("volume_mapping_missing");
        } else {
            if (pEsp.size !== 300 * MiB) geometryFailures.push("esp_size_bytes_" + pEsp.size + "_expected_" + (300 * MiB));
            if (pRe.size !== 2048 * MiB) geometryFailures.push("winre_size_bytes_" + pRe.size + "_expected_" + (2048 * MiB));
            var msrGap = pWin.offset - (pEsp.offset + pEsp.size);
            if (msrGap !== 16 * MiB) geometryFailures.push("msr_gap_bytes_" + msrGap + "_expected_" + (16 * MiB));
            var winreGap = pRe.offset - (pWin.offset + pWin.size);
            if (winreGap !== 0) geometryFailures.push("windows_winre_gap_bytes_" + winreGap + "_expected_0");
            var tailBytes = diskSize - (pRe.offset + pRe.size);
            if (tailBytes < 0 || tailBytes > 2 * MiB) geometryFailures.push("disk_tail_bytes_" + tailBytes + "_allowed_0_to_" + (2 * MiB));
            if (pWin.size <= 2048 * MiB) geometryFailures.push("windows_size_bytes_" + pWin.size + "_must_exceed_" + (2048 * MiB));
        }
        verdict("target.partition_sizes_exact", exact ? "PASS" : "FAIL",
                exact ? "ESP300_MSR16_WindowsRemainder_Recovery2048_end" : geometryFailures.join("__"));
        var diskpart = safeText(diskpartLog);
        var guidMatch = /Disk ID:\s*\{?([0-9a-fA-F-]{36})\}?/i.exec(diskpart);
        diskID = guidMatch ? guidMatch[1].toLowerCase() : "";
        var doc = xmlDoc(os + ":\\Windows\\System32\\Recovery\\ReAgent.xml");
        var node = doc.getElementsByTagName("ImageLocation").item(0);
        var offset = node ? Number(node.getAttribute("offset")) : -1;
        var guid = node ? String(node.getAttribute("guid")).replace(/[{}]/g, "").toLowerCase() : "";
        var path = node ? String(node.getAttribute("path")).toLowerCase() : "";
        var registered = mapping && !!diskID && guid === diskID &&
                         offset === pRe.offset && path === "\\recovery\\windowsre";
        verdict("recovery.reagent_target_offset", registered ? "PASS" : "FAIL",
                registered ? "WinRE_GUID_and_exact_offset_match_target_Recovery" : "ReAgent_GUID_or_offset_mismatch");
    } catch (e) {
        fatal("target.physical_volume_mapping", e);
        fatal("target.partition_sizes_exact", e);
        fatal("recovery.reagent_target_offset", e);
    }
})();
