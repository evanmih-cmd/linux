# Windows 11 Pro: ручное развёртывание на второй физический диск

**Статус 2026-10-09:** процедура **выполнена на двухдисковом стенде**, Windows 11 Pro впервые дошла до рабочего стола без запроса пароля. Полная приёмка всё ещё **НЕ ПРОЙДЕНА**: повторный вход, WinRE Enabled, Secure Boot и Offline защищённого диска из загруженной Windows не доказаны. На текущей проверке экран чёрный, Guest Control недоступен; без жёсткого выключения повторный запуск не выполнялся. Не объявлять production PASS.

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

После регистрации WinRE и копирования XML **не требуется снимать букву `R:`**. Это временная буква текущего WinPE, а не часть постоянной конфигурации Windows. У Recovery уже правильный GPT-тип и атрибуты. Не выполняем лишних операций с разделами.

### Учётная запись: без пароля, одинаково на VM и ASUS

**Новый канонический [Autounattend.xml](Autounattend.xml)** используется
**побайтово одинаковым** на VM и ASUS. Он создаёт ровно одну локальную
учётную запись `owner` (группа Administrators) **без элемента `Password`**.
На установочных носителях, в сценариях и в коде генератора **нет пароля
к этому аккаунту**. Его позднее задаёт сам владелец в установленной
Windows. `vmbench` из раннего стенда не является требуемой учётной записью
этой установки и не переносится в ASUS.

В XML **нет `AutoLogon`, `LogonCount` и ограничения числа входов**.
Используется штатное поведение Windows с единственным локальным
аккаунтом без пароля; подтверждение **автоматического, повторяемого
входа без пользовательских действий** на нашей сборке пока
**BLOCKED / NOT_PROVEN**. До установки на ASUS обязателен запуск
на стенде с этим **точным XML** и не менее двух последовательных
перезапусков/входов без пароля. Отдельно проверить, что после
установки владельцем собственного пароля Windows требует уже
этот пароль, а не продолжает входить автоматически. Это требование
выше любого статического теста XML.

Преднамеренно **не используем**:
- Unattend `AutoLogon/LogonCount`: Microsoft ограничивает число входов;
- значение `DefaultPassword` с фиктивным/пустым паролем через
  `Winlogon/AutoAdminLogon`: без отдельного теста это может приводить
  к неудачным автоматическим попыткам после установки владельцем пароля.

**Внимание:** старый ответный ISO стенда содержал тестовый пароль.
Он **не является допустимым установочным носителем** и не должен
копироваться на ASUS. Новый канонический XML не изменяет уже
установленную Windows задним числом: текущая VM всё ещё имеет
старую учётную запись до отдельного повторного развёртывания
или доверенной миграции. Наличие готового XML **не означает
успешной live-проверки беспарольного входа**.

## 5. Как запустить установленную Windows 11 Pro и завершить установку

После DISM образ Windows **уже записан на целевой диск**. Кнопку **Install now** в установщике Windows больше не нажимать; повторно запускать Windows Setup, выбирать разделы или применять WIM **не нужно**. Следующий этап — **первая загрузка развернутой ОС**, на которой Windows завершит инициализацию (specialize/OOBE).

### Перед перезагрузкой

- Успешно завершены DISM, BCDBoot `/s S: /f UEFI`, копирование и регистрация WinRE, копирование **точно** в `W:\Windows\Panther\Unattend.xml` (не `Unattended.xml`).
- Проверено наличие `S:\EFI\Microsoft\Boot\BCD` и `S:\EFI\Boot\bootx64.efi` **на целевом ESP**.
- Запущены штатные скрипты [AUDIT.CMD + EXTRA.JS](../winpe-audit/SCRIPT_README.md) на выбранных вручную физических дисках. Все доступные до первой загрузки проверки должны дать `FAIL=0`. `NOT_PROVABLE` допустим только для фактической загрузки/редакции/Secure Boot/WinRE Enabled и доказательств, требующих заранее снятого эталона SSD1 или доступа к сырым GPT CRC.
- Никаких новых `clean`, `format`, `shrink`, `create partition`, `bcdboot` или `reagentc /enable` сейчас не требуется. Защищённый SSD1 не изменять.

**На текущем стенде (2026-10-09):** автономный аудит из WinPE дал **40 PASS / 0 FAIL / 5 NOT_PROVABLE**; независимый Linux/VDI-аудит — **23 PASS / 0 FAIL**. Это принимает подготовку диска и файлов, **но не подтверждает состоявшуюся загрузку Windows**.

### Запуск из открытой командной строки WinPE

Ввести **одну** команду:

```cmd
wpeutil reboot
```

Это перезагружает машину. **Дальше запускать ОС должен UEFI-загрузчик целевого SSD/RAID LUN**, а не Windows Setup с DVD.

1. **Если появится `Press any key to boot from CD or DVD...` — ничего не нажимать.** Дать прошивке перейти к загрузке с диска.
2. **На VM:** должен использоваться `Desktop-Windows-11-Pro-TwoDisk`, целевой `SATA 1 / 96 GiB`; защищённый `SATA 0 / 8 GiB` не переставлять и не отключать ради обхода теста. Ранее установленный приоритет UEFI `Boot0005` (целевой) перед `Boot0004` (защищённый) следует **проверять фактической загрузкой**, не считать гарантией. Если VM снова загрузится с установочного ISO, выбрать **именно целевой диск/EFI-загрузчик** через firmware Boot Manager или штатный интерфейс VM отключить *только установочный оптический носитель*, после чего повторить загрузку. Не запускать GUI Setup повторно.
3. **На ASUS:** использовать firmware Boot Menu и вручную выбрать **второй физический SSD / целевой AMD RAID LUN**, не пункт Windows Home на SSD1. Номера дисков и название UEFI-записи могут отличаться от VM. Если однозначной записи для целевого диска нет, **остановиться и зафиксировать проблему**, а не менять загрузчик/ESP первого SSD. `BCDBoot /s` намеренно не создавал запись UEFI NVRAM; наличие файлов на ESP **ещё не гарантирует** отображение RAID LUN в Boot Menu.
4. При корректной загрузке появится первая инициализация Windows 11 Pro (подготовка устройств, `specialize`, OOBE). Возможны повторные перезагрузки. **Не возвращаться в установщик ISO**, не выбирать диски заново.
5. Если вместо первой инициализации появилась ошибка загрузки, UEFI Shell или снова WinPE, сохранить экран/ошибку. Не запускать `Startup Repair`, `bcdboot` или другую запись в ESP без диагностики целевого пути.

**Примечание:** состояние `Offline`, выставленное SSD1 внутри WinPE, не следует считать доказанно сохраняющимся после перезагрузки. Независимость загрузки надо проверять по фактическому UEFI boot device и состоянию загруженной Windows, а не по одному `offline disk` до перезагрузки.

### Приёмка после первого запуска

После выхода на рабочий стол **именно Windows 11 Pro**:

```cmd
reagentc /info
```

Статус должен быть `Enabled`, расположение Windows RE — на Recovery-разделе **целевого** диска. Далее в установленной Windows проверить редакцию Pro, `msinfo32` → `Secure Boot State: On`, фактический загрузочный диск и сохранность SSD1. Скрипт `AUDIT.CMD` предназначен **только для WinPE**; прежний аргумент `--phase booted` собственного EXE больше не используется. **Только после отдельной приёмки загрузившейся Windows** считать двухдисковую установку принятой.

## 6. Критерии принятия

- На целевом диске **ровно один ESP**, MSR 16 МиБ, Windows NTFS, последний WinRE **2048 МиБ**, правильные GPT ID и атрибуты.
- На ESP **своего** целевого диска находятся Microsoft EFI-загрузчик и BCD.
- Целевой диск самостоятельно загружает Windows 11 Pro через firmware Boot Menu, без зависимости от SSD1; Secure Boot остаётся включённым.
- `reagentc /info` в загруженной Pro подтверждает Enabled и расположение WinRE на целевом разделе.
- SSD1: GPT и контрольные данные неизменны; во время опасных операций он Offline.
- Реальная аппаратная поддержка RAID и firmware boot на ASUS — отдельная аппаратная проверка, не утверждать PASS по VirtualBox.
- **Текущий статус:** первый запуск desktop наблюдался; перечисленные runtime-условия остаются `NOT PROVEN`, ASUS `NO-GO`.

## Первичные источники Microsoft

- [UEFI/GPT partitions](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/configure-uefigpt-based-hard-drive-partitions)
- [Microsoft CreatePartitions-UEFI example](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/oem-deployment-of-windows-desktop-editions-sample-scripts)
- [Capture and apply Windows](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/capture-and-apply-windows-using-a-single-wim)
- [Capture/apply system and recovery](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/capture-and-apply-windows-system-and-recovery-partitions)
- [BCDBoot](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/bcdboot-command-line-options-techref-di)
- [REAgentC](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/reagentc-command-line-options)


## Независимая приёмка из установочной WinPE

**Актуальный аудитор для ASUS и VirtualBox — только штатные скрипты
[AUDIT.CMD + EXTRA.JS](../winpe-audit/SCRIPT_README.md).**
Копировать на флешку оба текстовых файла. В официальной WinPE запускать
`AUDIT.CMD` с вручную установленными номерами физических дисков и буквами
ESP/Windows/WinRE/канонического XML. Сценарии строго read-only по отношению
к обоим SSD; используются только встроенные WinPE CMD, DiskPart, BCDEdit,
FSUTIL, ReAgentC, Windows Script Host, WMI и MSXML.

Проверяется полный GPT layout, целевой ESP/BCD, WinRE 2048 МиБ в конце,
файлы Windows, точные byte-offset и принадлежность томов целевому диску,
GUID регистрации WinRE, побайтовая идентичность канонического
`Unattend.xml`. В тестовой WinPE: **29 PASS / 0 FAIL / 6 NOT_PROVABLE**,
последние — неразрешимые до первого запуска ОС или без заранее
снятого эталона SSD1/сырых GPT-секторов. После первой загрузки требуется
отдельная проверка работающей Pro, WinRE и Secure Boot.

Предыдущее самодельное приложение `winpe-audit.exe` **отвергнуто и не
используется**. Независимый Linux/VDI harness и `parity.py` сохранены.
