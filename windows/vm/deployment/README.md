# Windows 11 Pro: ручное развёртывание на второй физический диск

**Статус:** согласованная процедура, **на двухдисковом стенде ещё не проверена до рабочего desktop**. Не объявлять PASS до проверки независимой загрузки и WinRE.

**Жёсткий контракт:** никаких исполняемых сценариев разметки, `DiskPart /s`, PowerShell/`.cmd`/`.bat`, автоматически выбирающих, очищающих или форматирующих диск, ни в VM, ни на ASUS. Каждый шаг выполняется оператором **отдельной командой** в WinPE. Автоматизированная конфигурация после установки допускается, но не управление разметкой. `DEPLOY.CMD` из предыдущей попытки **отвергнут, не запускать**.

## 1. До удаления любых разделов

Загрузить **официальный ISO Windows 11** в UEFI-режиме и открыть командную строку WinPE (`Shift+F10`). Найти существующий SSD1 по размеру и `detail disk`, вручную перевести его Offline. Затем выбрать целевой диск по **фактической идентичности**, не по постоянному номеру.

На *тестовом стенде* защищённый диск — **Disk 0, 8 GiB**, целевой — **Disk 1, 96 GiB**. Это **НЕ** обещанные номера на ASUS; на ASUS идентификация выполняется заново.

В интерактивном `diskpart`:

```cmd
diskpart
list disk
select disk 0
detail disk
offline disk
list disk
select disk 1
detail disk
```

**Стоп-контроль:** выбранный диск должен быть целевым, защищаемый SSD1 — Offline. Если размеры, модели, интерфейсы или состояние не соответствуют ожидаемым, **не вводить `clean`**. Не переносить `select disk 1` с VM на ASUS автоматически.

## 2. Четыре раздела GPT/UEFI; WinRE ровно 2048 МиБ в конце

Продолжая **в том же интерактивном DiskPart**, после явной проверки целевого диска:

```cmd
clean
convert gpt

create partition efi size=300
format quick fs=fat32 label="System"
assign letter=S

create partition msr size=16

create partition primary
shrink desired=2048 minimum=2048
format quick fs=ntfs label="Windows"
assign letter=W

create partition primary
format quick fs=ntfs label="Recovery"
assign letter=R
set id=de94bba4-06d1-4d40-a16a-bfd50179d6ac
gpt attributes=0x8000000000000001

list partition
list volume
exit
```

**Каждую строку вводить вручную и проверить результат.** Не продолжать после ошибки DiskPart. `create partition primary` на GPT означает Microsoft Basic Data (для раздела WinRE тип затем заменён через `set id`), а не MBR Primary/Extended.

Последовательность `create partition primary` → `shrink` → `format` для Windows-раздела — из образца Microsoft CreatePartitions-UEFI, но здесь `shrink desired=2048 minimum=2048` фиксирует согласованные **2 ГиБ**. В результате **WinRE — четвёртый и последний раздел диска** без свободного пространства после него:

| № | Тип GPT | Размер | Буква в WinPE |
| --- | --- | --- | --- |
| 1 | ESP, FAT32 | 300 МиБ | S: |
| 2 | MSR | 16 МиБ | нет |
| 3 | Windows, NTFS | остаток перед WinRE | W: |
| 4 | Microsoft Recovery, NTFS | **2048 МиБ, физический конец** | R: временно |

Размер ESP 300 МиБ совместим с минимальным размером для 4Kn; 16 МиБ MSR и расположение WinRE непосредственно за Windows соответствуют документации Microsoft.

## 3. Ручное развёртывание образа (после проверки разметки)

В WinPE узнать фактическую букву официального DVD/ISO через `diskpart` → `list volume` → `exit`. **Ниже E: — пример, не фиксированная буква.**

```cmd
dir E:\sources\install.wim
dism /Get-ImageInfo /ImageFile:E:\sources\install.wim
```

Убедиться, что выбран **Windows 11 Pro**, затем применить соответствующий образ по имени (если имя в ISO отличается, не угадывать индекс):

```cmd
dism /Apply-Image /ImageFile:E:\sources\install.wim /Name:"Windows 11 Pro" /ApplyDir:W:\
```

Дождаться `The operation completed successfully`.

```cmd
bcdboot W:\Windows /s S: /f UEFI
dir S:\EFI\Microsoft\Boot\BCD
dir S:\EFI\Boot\bootx64.efi
bcdedit /store S:\EFI\Microsoft\Boot\BCD /enum all
```

`/s S:` явно указывает **собственный ESP целевого диска**, без поиска ESP на SSD1. С `/s` BCDBoot не создаёт запись UEFI NVRAM; независимую загрузку из firmware Boot Menu надо доказать отдельно на ASUS.

```cmd
md R:\Recovery\WindowsRE
copy W:\Windows\System32\Recovery\Winre.wim R:\Recovery\WindowsRE\Winre.wim
W:\Windows\System32\reagentc.exe /setreimage /path R:\Recovery\WindowsRE /target W:\Windows
W:\Windows\System32\reagentc.exe /info /target W:\Windows
```

В WinPE `reagentc /info` может показывать Disabled до `specialize`; после первой загрузки подтвердить Enabled. Если копирование, `bcdboot` или `reagentc /setreimage` завершаются ошибкой, **остановиться**, не перезагружаться «на авось».

## 4. Один существующий Autounattend.xml и первая загрузка

Определить букву DVD с **тем же каноническим `Autounattend.xml`** (здесь `F:` только пример):

```cmd
dir F:\Autounattend.xml
md W:\Windows\Panther
copy F:\Autounattend.xml W:\Windows\Panther\Unattend.xml
```

Для DISM-развёртывания `windowsPE`-проход XML не выполняется — разметка и применение WIM сделаны вручную; применимые `specialize` и `oobeSystem` настройки будут использованы после старта ОС. **Никаких отдельных test/prod XML** и `DiskID` в XML.

После регистрации WinRE и копирования XML букву R: можно убрать вручную, при этом не теряя выбранный диск и раздел:

```cmd
diskpart
list disk
select disk 1
list partition
select partition 4
detail partition
remove letter=R
exit
```

`select disk 1` здесь — **только пример стенда**. Перед `select partition 4` проверить реальную разметку; не переносить номера на ASUS без проверки.

После успешных команд — `wpeutil reboot`. Не подтверждать оптический boot prompt, проверить загрузку именно **с целевого физического диска**. Сохранность оригинального SSD1 подтверждать независимой проверкой, не по одному сообщению Setup.

## 5. Критерии принятия

- На целевом диске **ровно один ESP**, MSR 16 МиБ, Windows NTFS, последний WinRE **2048 МиБ**, правильные GPT ID и атрибуты.
- На ESP **своего** целевого диска находятся Microsoft EFI-загрузчик и BCD.
- Целевой диск самостоятельно загружает Windows 11 Pro через firmware Boot Menu, без зависимости от SSD1; Secure Boot остаётся включённым.
- `reagentc /info` в загруженной Pro подтверждает Enabled и расположение WinRE на целевом разделе.
- SSD1: GPT и контрольные данные неизменны; во время опасных операций он Offline.
- Реальная аппаратная поддержка RAID и firmware boot на ASUS — отдельная аппаратная проверка, не утверждать PASS по VirtualBox.
- **Текущий статус до нового live-run: NOT PROVEN.**

## Первичные источники Microsoft

- [UEFI/GPT partitions](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/configure-uefigpt-based-hard-drive-partitions)
- [Microsoft CreatePartitions-UEFI example](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/oem-deployment-of-windows-desktop-editions-sample-scripts)
- [Capture and apply Windows](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/capture-and-apply-windows-using-a-single-wim)
- [Capture/apply system and recovery](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/capture-and-apply-windows-system-and-recovery-partitions)
- [BCDBoot](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/bcdboot-command-line-options-techref-di)
- [REAgentC](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/reagentc-command-line-options)
