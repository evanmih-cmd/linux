# AMD RAID: boot-critical драйверы WinOps (WinPE / Windows / WinRE)

**Обязательное дополнение к [основной инструкции](README.md), а не её замена.** Старые разделы 0–6 с ручной разметкой, DISM, ESP/BCD, WinRE, XML и аудитом остаются действующими. Применяется только к физическому ASUS FA401EA при использовании RAID LUN `WinOps` на SSD2 (Lexar NM790); на VirtualBox без AMD RAID не требуется.

**Наблюдение, ещё не PASS:** исходная WinPE показывала физическую NM790 ~3.7 TB как Unknown/MBR вместо целевой LUN; `drvload rcbottom\rcbottom.inf` потребовал reboot. Владелец уже подготовил изменённый `boot.wim` в WinHome и записывал его на существующую USB. Загрузка именно RAID LUN с обновлённой флэшки пока не подтверждена.

## Обязательные три среды

| Этап | Когда | Операция |
|---|---|---|
| 1. Установочная WinPE | **До** загрузки установочной USB | Встроить проверенные AMD RAID INF в Windows Setup **index `boot.wim`** |
| 2. Новая WinOps | После `DISM /Apply-Image`, **до первого boot** | Добавить те же INF в **offline `W:\Windows`**, подтвердить boot-critical |
| 3. WinRE | **До** копирования `Winre.wim` на раздел `R:` | Смонтировать **WinRE WIM**, добавить те же INF, сохранить WIM |

**Это разные образы.** Наличие драйвера в WinPE не переносит его в Windows либо WinRE. `DISM /Get-Drivers` доказывает staging пакета, но ещё **не** его пригодность для загрузки. Не менять службы реестра `Start=0` вручную, не применять `ForceUnsigned`.

**Источник:** официальный AMD RAID x64 пакет ASUS для конкретной FA401EA. На имеющейся флэшке он назывался `Raid_ROG_AMD_J_V9.3.3.00267_46073_20261010165456` и содержал `rcbottom\rcbottom.inf`, `rcraid\rcraid.inf`, `rccfg\rccfg.inf`. Перед работой подтвердить именно официальный пакет, INF/подписи, архитектуру amd64 и PCI Hardware IDs конкретного контроллера. Буквы ниже **примеры**, уточнять заново в каждой среде. **Никаких exe-установщиков.**

## 1. Подготовка boot.wim в WinHome: только если требуется переделать USB

**Если обновлённый `boot.wim` уже записан, не повторять и тем более не создавать «оригинал» из модифицированной USB!** При первой подготовке сохраняются **две отдельные копии из исходной Microsoft USB**: `boot.original.wim` (никогда не изменять) и `boot.wim` (рабочая). Если USB уже модифицирована, для восстановления исходника нужен прежний реально сохранённый `boot.original.wim` либо исходный официальный ISO.

CMD администратора в WinHome; в примере `U:` — фактическая буква USB. Все операции проводятся в **новом пустом** каталоге; существующие рабочие каталоги не затирать.

```cmd
set "MEDIA=U:"
set "RAID=%MEDIA%\DRIVERS\Raid_ROG_AMD_J_V9.3.3.00267_46073_20261010165456"
dir "%RAID%\rcbottom\rcbottom.inf"
dir "%RAID%\rcraid\rcraid.inf"
dir "%RAID%\rccfg\rccfg.inf"
dism /Get-WimInfo /WimFile:"%MEDIA%\sources\boot.wim"
```

Сначала проверить фактические индексы Microsoft `boot.wim`. Типично **index 2 = Microsoft Windows Setup**; это **не** константа. По Microsoft драйвер, добавленный в один индекс, **не переносится** в другой. При исходном, ещё неизменённом носителе:

```cmd
md C:\WinOps-WinPE
md C:\WinOps-WinPE\mount
copy /v "%MEDIA%\sources\boot.wim" C:\WinOps-WinPE\boot.original.wim
copy /v C:\WinOps-WinPE\boot.original.wim C:\WinOps-WinPE\boot.wim
certutil -hashfile C:\WinOps-WinPE\boot.original.wim SHA256
dism /Mount-Image /ImageFile:C:\WinOps-WinPE\boot.wim /Index:2 /MountDir:C:\WinOps-WinPE\mount
dism /Image:C:\WinOps-WinPE\mount /Add-Driver /Driver:"%RAID%\rcbottom\rcbottom.inf"
dism /Image:C:\WinOps-WinPE\mount /Add-Driver /Driver:"%RAID%\rcraid\rcraid.inf"
dism /Image:C:\WinOps-WinPE\mount /Add-Driver /Driver:"%RAID%\rccfg\rccfg.inf"
dism /Image:C:\WinOps-WinPE\mount /Get-Drivers /Format:List
```

**STOP при любой ошибке / неподтверждённом индексе**; не фиксировать испорченный WIM. По результату `/Get-Drivers` определить OEM-имена трёх пакетов и выполнить `dism /Image:C:\WinOps-WinPE\mount /Get-DriverInfo /Driver:oemNN.inf` **для каждого, подставляя реальное имя**; сверить `Boot Critical` для `rcbottom` и `rcraid`, подписанный x64 пакет и Hardware IDs. Это свойство пакета; доступность настоящей LUN доказывается только загрузкой WinPE на ASUS. Если WIM уже смонтирован и какой-то `Add-Driver` завершился ошибкой, откатить только рабочий mount командой `dism /Unmount-Image /MountDir:C:\WinOps-WinPE\mount /Discard`; резервный `boot.original.wim` не меняется. После трёх успешных `Add-Driver` и проверки фактических пакетов:

```cmd
dism /Unmount-Image /MountDir:C:\WinOps-WinPE\mount /Commit
dism /Get-WimInfo /WimFile:C:\WinOps-WinPE\boot.wim
certutil -hashfile C:\WinOps-WinPE\boot.wim SHA256
```

Только при наличии **исходного** `boot.original.wim`, свободного места на USB и проверенной буквы `MEDIA` заменить **один** файл:

```cmd
copy /v C:\WinOps-WinPE\boot.wim "%MEDIA%\sources\boot.wim"
certutil -hashfile "%MEDIA%\sources\boot.wim" SHA256
```

Хеш записанного файла должен **совпасть с хешем рабочей** `boot.wim`. Оригинал сохраняется на WinHome; не трогать остальные файлы Microsoft (включая `sources\install.*`), USB не пересоздавать.

## 2. WinPE: доказать виртуальную LUN до любых записей на диски

Из Boot Menu ASUS (`Esc`) загрузить USB, `Shift+F10`, только чтение:

```cmd
diskpart
rescan
list disk
exit
```

**PASS:** виден отдельный логический RAID-диск именно того размера, который назначен `WinOps` в UEFI/RAIDXpert2. Дополнительно вручную `detail disk` для каждого нужного устройства, зафиксировать действительные номера после загрузки драйверов. **STOP:** виден лишь физический NVMe ~3.7 TB как Unknown/MBR. AMD официально предупреждает: попытки удалять/форматировать разделы физического NVMe без драйвера могут уничтожить RAID metadata. Не применять `clean`/`convert gpt` к такому представлению.

До ручной разметки в [основном runbook, разделы 1–2](README.md) идентифицировать и перевести защищаемый SSD1/WinHome **Offline**, убедиться, что выбран именно WinOps LUN. Не переносить номера Disk 0/Disk 1 из VM или прошлой WinPE. Далее разметка вручную: ESP 300 MiB, MSR 16 MiB, Windows, WinRE 2048 MiB в конце.

## 3. После DISM Apply-Image: добавить загрузочный RAID в установленную WinOps

**Точка вставки в `3 README:** после успешного `dism /Apply-Image`, **до `bcdboot` и до первой перезагрузки**. `W:` — проверенный Windows NTFS **WinOps**, `D:` — только пример USB в WinPE. Никаких операций с SSD1.

```cmd
dir W:\Windows\System32\config\SYSTEM
set "RAID=D:\DRIVERS\Raid_ROG_AMD_J_V9.3.3.00267_46073_20261010165456"
dir "%RAID%\rcbottom\rcbottom.inf"
dir "%RAID%\rcraid\rcraid.inf"
dir "%RAID%\rccfg\rccfg.inf"
dism /Image:W:\ /Add-Driver /Driver:"%RAID%\rcbottom\rcbottom.inf"
dism /Image:W:\ /Add-Driver /Driver:"%RAID%\rcraid\rcraid.inf"
dism /Image:W:\ /Add-Driver /Driver:"%RAID%\rccfg\rccfg.inf"
dism /Image:W:\ /Get-Drivers /Format:List
```

После **каждой** команды DISM требовать успешное завершение. По полям `Original File Name` / `Published Name` сопоставить каждому драйверу его новый `oemNN.inf`, **не угадывать номер**. Затем для **каждого** фактического имени:

```cmd
dism /Image:W:\ /Get-DriverInfo /Driver:oemNN.inf
```

`oemNN.inf` здесь — **шаблон, его нужно заменить**. В отчёте DISM сверить:
- `rcbottom` и `rcraid` — действительные компоненты загрузочного RAID-пути. Ожидается **`Boot Critical: Yes`**, архитектура **amd64**, подходящие Hardware ID / Service Name / DriverVer. Если `No` или несовпадающая архитектура, **STOP**, изучить INF и аппаратную привязку. Не «чинить» вручную `StartType` в реестре.
- `rccfg` — конфигурационный компонент; **не требовать** от него `Boot Critical: Yes`.
- Само `Boot Critical: Yes` **не гарантирует** загрузку: это проверка свойств пакета; окончательный PASS — только реальная загрузка и рабочий RAID-контроллер.

**Не путать:** `DISM /Image:W:\ /Add-Driver` сразу добавляет пакет в развёрнутый offline Windows; `/Unmount /Commit` для самой `W:\Windows` **не нужен**. Однако у WinRE внутри неё есть собственный WIM — следующий этап.

## 4. WinRE: добавить RAID до старой команды copy на R:

**Вставить между `bcdboot` и существующими в `3 README `md R:\Recovery\WindowsRE` / `copy ...Winre.wim`.** WinRE образ расположен в `W:\Windows\System32\Recovery\Winre.wim` целевой WinOps. Не извлекать его из другой системы и не писать в SSD1. Подтвердить, что `RAID` из предыдущего этапа всё ещё указывает на фактический USB.

```cmd
dir /a W:\Windows\System32\Recovery\Winre.wim
md W:\WinOps-WinRE-Mount
md W:\WinOps-DISM-Scratch
dism /Get-ImageInfo /ImageFile:W:\Windows\System32\Recovery\Winre.wim
```

**STOP**, если WIM отсутствует, index 1 не подтверждён, каталог монтирования не пуст или недостаточно места на W:. Если именно атрибуты read-only/system/hidden на WinOps препятствуют монтированию, сначала посмотреть `attrib W:\Windows\System32\Recovery\Winre.wim`; при необходимости снять их **с целевого файла WinOps** командой `attrib -r -h -s W:\Windows\System32\Recovery\Winre.wim` и повторить Mount-Image. Не трогать WinHome.

```cmd
dism /Mount-Image /ImageFile:W:\Windows\System32\Recovery\Winre.wim /Index:1 /MountDir:W:\WinOps-WinRE-Mount /ScratchDir:W:\WinOps-DISM-Scratch
dism /Image:W:\WinOps-WinRE-Mount /Add-Driver /Driver:"%RAID%\rcbottom\rcbottom.inf" /ScratchDir:W:\WinOps-DISM-Scratch
dism /Image:W:\WinOps-WinRE-Mount /Add-Driver /Driver:"%RAID%\rcraid\rcraid.inf" /ScratchDir:W:\WinOps-DISM-Scratch
dism /Image:W:\WinOps-WinRE-Mount /Add-Driver /Driver:"%RAID%\rccfg\rccfg.inf" /ScratchDir:W:\WinOps-DISM-Scratch
dism /Image:W:\WinOps-WinRE-Mount /Get-Drivers /Format:List
```

По `Published Name` проверить реальные три INF и для каждого реального `oemNN.inf` выполнить `dism /Image:W:\WinOps-WinRE-Mount /Get-DriverInfo /Driver:oemNN.inf`. Проверить boot-critical **именно на WinRE WIM** для `rcbottom` и `rcraid` и правильные x64/HW IDs; `rccfg` не обязан быть boot-critical. Только после этого:

```cmd
dism /Unmount-Image /MountDir:W:\WinOps-WinRE-Mount /Commit /ScratchDir:W:\WinOps-DISM-Scratch
dism /Get-ImageInfo /ImageFile:W:\Windows\System32\Recovery\Winre.wim
```

При ошибке **не копировать** WinRE на R: и не перезагружаться. `/Discard` допустим только как осмысленный откат ещё смонтированного **WinRE**; не пытаться замаскировать провал драйвера. После успеха выполнить прежние строки основного `3: `md R:\Recovery\WindowsRE`, `copy W:\Windows\System32\Recovery\Winre.wim R:\Recovery\WindowsRE\Winre.wim`, `reagentc /setreimage` / `info`. Старые команды остались верными, но теперь копируют **уже обслуженный** WIM.

## 5. Обязательная приёмка

- До reboot: WinPE распознала виртуальную WinOps LUN; Windows и WinRE содержат проверенные storage INF; `Boot Critical` подтверждён для компонентов загрузочного пути; обе DISM-монтировки завершены; WinOps имеет свой ESP/BCD и WinRE; WinPE AUDIT — без FAIL по доступным проверкам; WinHome не изменена.
- Первый boot через firmware Boot Menu **именно с WinOps LUN**, не с SSD1. Отсутствие `INACCESSIBLE_BOOT_DEVICE` и рабочего Windows desktop — начальный PASS, но не полная аппаратная приёмка.
- После boot: в Device Manager AMD-RAID Bottom Device / AMD-RAID Controller / AMD-RAID Config Device, `reagentc /info` = Enabled. Проверить **доступ к массиву из Windows RE**, затем повторную нормальную загрузку и отдельно загрузку WinHome. Продолжить `5–`6 основного runbook и вести результаты в [issue #9](https://github.com/evanmih-cmd/linux/issues/9).
- Если первый boot неудачен: **не форматировать WinHome / физическую NM790**, сохранить вывод ошибки, вернуться в проверенную WinPE, исследовать драйвер/BCD, не запускать очередную чистую установку вслепую.

## Первоисточники

- [AMD RAID Quick Start Guide for Windows, Rev 1.20, May 2026](https://docs.amd.com/api/khub/documents/Zy_ez138iRvYDQQqWYA0ug/content), Chapter 5 — последовательность `rcbottom → rcraid → rccfg`, риск уничтожить RAID metadata и ограничение `drvload`.
- [Microsoft: Limitations of $WinPeDriver$](https://learn.microsoft.com/en-us/troubleshoot/windows-client/setup-upgrade-and-drivers/limitations-dollar-sign-winpedriver-dollar-sign) — обработка нужного индекса `boot.wim`.
- [Microsoft: Add and Remove Drivers](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/add-and-remove-drivers-to-an-offline-windows-image?view=windows-11) и [DISM Driver Inventory](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/take-inventory-of-an-image-or-component-using-dism) — offline драйверы, OEM INF и поле `Boot Critical`.
- [Microsoft: Customize Windows RE](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/customize-windows-re?view=windows-11) — boot storage drivers в WinRE.
- [Microsoft: Drvload](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/drvload-command-line-options?view=windows-11) — reboot-request incompatibility.
