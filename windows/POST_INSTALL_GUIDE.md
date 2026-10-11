# WinOps — post-install: порядок настройки Windows 11 Pro

**Статус:** рабочая инструкция для ASUS TUF A14 FA401EA (WinOps / `SECUREWS`) и того же канонического Windows 11 Pro на стенде. Начинается **после** того, как Windows уже установлена и впервые загрузилась. Если SECUREWS уже настроена частично, **не повторяйте выполненную установку, OOBE или операции над RAID/GPT**: проверяйте текущий факт и переходите к ещё не завершённому этапу.

**Жёсткий порядок:**

```text
Штатная Windows → штатные драйверы и Windows Update → проверенная рабочая система
       ↓
System Protection → точка восстановления «WinOps - clean Windows ...»
       ↓
WinOps-specific configuration (DSC / software) → Microsoft baseline (LGPO)
       ↓
Перезагрузка и функциональная приёмка → завершение настройки → offline system image
```

**ВНИМАНИЕ:** этап 3 **нельзя** начинать до успешного завершения этапов 1 и 2. Никаких попыток «сразу закрутить гайки», сторонних твикеров, UEFI-lock, переразметки и повторной установки ради post-install. Штатное обновление Windows/драйверов — не наша отдельная security-политика, а обязательная подготовка поддерживаемой ОС. Применение DSC+LGPO без точки восстановления — отклонение от утверждённого порядка.

Ниже `U:` — **пример**, определить фактическую букву USB заново в установленной Windows. Все секреты выбирает владелец, **не** сохранять PIN, пароль, 48-значный BitLocker recovery key, seed phrases, содержимое KDBX или приватные ключи в Git, на установочной USB, в скриптах, логах и issue.

## Этап 1. Обычная Windows: OOBE, драйверы, обновления, стабильность

**Цель:** получить полноценную *штатную* Windows 11 Pro, которая загружается, обновляется и нормально работает **до** применения наших специальных политик и программ.

1. **Первый вход и базовая учётная запись.** Завершить Windows OOBE; войти под единственным каноническим локальным `owner`. При необходимости назначить владельцем длинный пароль учётной записи; **обязательно** настроить Windows Hello PIN в **Параметры → Учётные записи → Варианты входа**. На реальном ASUS настроить Hello Face, если совместимые IR-камера и ESS доступны, проверить вход Face и запасной PIN. Подтвердить работоспособность *обычного* повышения прав/UAC до переключения режима Administrator Protection. Это **ещё не** доказывает защищённое повышение через `ADMIN_owner`.
2. **Проверить ОС, активацию и локализацию.** Windows 11 **Pro, 26H2**; en-US интерфейс; форматы de-DE; часовой пояс `W. Europe Standard Time`; клавиатуры только US + RU. Если регион добавил немецкую раскладку, удалить её штатными Параметрами. Подтвердить активацию отдельно от подлинности образа (нет обязанности устанавливать ключ из неофициального источника).
3. **Официальные аппаратные драйверы.** Проверить в Device Manager отсутствие неизвестных/ошибочных устройств. Поставить/обновить только подходящие **подписанные** драйверы AMD/ASUS и нужных устройств (чипсет, AMD RAID, графика, WLAN/Bluetooth, Ethernet/Realtek, IR/биометрия, аудио, тачпад и т. п.) через штатный Windows Update и официальные поставки ASUS/AMD. Проверять модель FA401EA, HW ID, совместимость ОС и конкретный пакет; не ставить Armoury Crate/MyASUS или сомнительные драйверпаки лишь ради настройки драйверов. **Не менять driver stack работающего RAID вслепую**: загрузочный драйвер в установленной Windows, WinPE USB и WinRE — разные среды; см. [RAID supplement](vm/deployment/AMD_RAID_BOOT.md). Если драйвер вызывает нестабильность или отказ загрузки — **STOP**, не переходить к hardening.
**ASUS OEM-компоненты: точный состав для FA401EA.** Отсутствие «Unknown device» в Device Manager не равнозначно наличию и функциональности ASUS System Control Interface. **На этапе 1** сохранить штатные аппаратные драйверы и проверить, что установлен подходящий подписанный **ASUS System Control Interface v3** (возможна уже установленная версия из Windows Update); при отсутствии — установить только этот драйвер с [официальной страницы FA401EA](https://www.asus.com/us/laptops/for-gaming/tuf-gaming/asus-tuf-gaming-a14-2026-fa401ea/helpdesk_download?model2Name=FA401EA), без MyASUS. Версии драйверов выбирать по совместимости с конкретной системой, не по одному имени приложения. Штатная проверка без установки ПО: `Get-PnpDevice -PresentOnly | Where-Object FriendlyName -like '*ASUS System Control Interface*'` в PowerShell, затем функционально проверить аппаратные события после настройки G-Helper.

| Компонент | Решение WinOps | Когда / зачем |
| --- | --- | --- |
| **ASUS System Control Interface v3** | **Оставить / установить, если отсутствует** | Аппаратный ACPI/WMI-драйвер, необходимый G-Helper; **не путать с MyASUS** |
| **G-Helper** (сторонняя утилита, [официальный upstream](https://github.com/seerge/g-helper)) | **Использовать вместо ASUS GUI** | Только **этап 3**, после restore checkpoint: заряд 60% при поддержке железом, Fn/режимы, отдельно принятые SYSTEM one-shot и обычный пользовательский GUI |
| **Armoury Crate** / **MyASUS** | **Не устанавливать** | Лишний OEM GUI и сопутствующие фоновые службы при выбранном G-Helper |
| **Armoury Crate Control Interface** | **Не устанавливать дополнительно** | Не обязательный компонент выбранного G-Helper-пути; если уже поставлен Windows Update как драйвер, **не удалять вслепую** |
| **ASUS Smart Display Control** | **Не устанавливать** | Может конкурировать с G-Helper за частоту обновления дисплея |
| **ASUS Optimization Service** (`ASUSOptimization`) | **Не оставлять параллельным обработчиком Fn** | **На этапе 3**, после запуска и проверки G-Helper, штатно остановить/отключить именно конфликтующую службу; не удалять нужный аппаратный драйвер и не отключать все ASUS-службы без разбора |
| **ASUS Keyboard Hotkeys / ATK Package** | **Не устанавливать как дополнительный пакет поверх SCI v3** | Старые/альтернативные модельные пути; нужны только при доказанной необходимости и согласно драйверной странице конкретной модели |
| **ASUS Live Update / Software Manager / Link / System Diagnosis и аналогичный OEM автософт** | **Не устанавливать** | Не нужны вторые обновляторы, OEM-агенты и синхронизация |
| **AMD RAIDXpert2** | **По необходимости, отдельно от ASUS** | Утилита управления RAID, **не обязательная для работы уже загружающегося RAID**; не заменять boot-critical AMD RAID-драйверы установщиком ради GUI |

Не пытаться решать эту задачу установкой всего раздела **Utilities** из ASUS Support. **До точки восстановления (этап 2) не включать G-Helper и не отключать ASUSOptimization**: этап 1 должен подтверждать стабильную штатную Windows. Источники: [ASUS FA401EA downloads](https://www.asus.com/us/laptops/for-gaming/tuf-gaming/asus-tuf-gaming-a14-2026-fa401ea/helpdesk_download?model2Name=FA401EA), [G-Helper Requirements](https://github.com/seerge/g-helper/wiki/Requirements), [G-Helper FAQ](https://github.com/seerge/g-helper/wiki/FAQ).

4. **Windows Update до актуального поддерживаемого состояния.** `Параметры → Windows Update → Проверить наличие обновлений`. Установить доступные **стабильные** quality/security/Defender обновления и применимые поддерживаемые драйверы, при необходимости вручную перезагрузиться (включая промежуточные reboot), затем повторять scan, пока не останется обязательных ожидающих обновлений. **Preview/optional updates не являются обязательным gate** и не применяются автоматически ради галочки. **BIOS/UEFI firmware обновлять только по отдельному решению владельца**, не включать обновления firmware в обычный пакет Windows Update. Не применять собственные сервисы/задачи блокировки reboot: штатные политики Windows ограничены своим документированным поведением.
5. **Проверить работу до вмешательства.** После финальной обычной перезагрузки: Windows входит в `owner`, работает Hello, штатное повышение прав доступно, сеть и звук/IR/тачпад функционируют, Device Manager без необъяснимых ошибок, `msinfo32` показывает Secure Boot On; `reagentc /info` указывает на работающую регистрационную конфигурацию Windows RE; системный том остаётся на WinOps RAID LUN, WinHome/SSD1 не трогалась. На уже установленной ASUS **не менять GPT, WinRE и BitLocker**, если их текущее состояние корректно. `reagentc /info = Enabled` показывает регистрацию, **не доказывает** фактическую загрузку WinRE.

**Стоп-критерий этапа 1:** Windows Update/драйверная установка ещё выполняется, есть запрос на обязательный reboot, Windows нестабильна, RAID не распознаётся, нет работающего Hello/elevation или непонятно состояние обновления. **Сначала решить штатную проблему; никакого DSC/LGPO.** При существующем ASUS со staged/незавершённым DISM/CBS не запускать второй установщик поверх первого: выяснить фактический exit code/package state.

## Этап 2. Контрольная точка ЧИСТОЙ штатной Windows

**Сделать ПОСЛЕ этапа 1, но СТРОГО ДО всех WinOps-specific изменений.** Это реальная локальная точка восстановления операционной системы, **не** Git-коммит, не запись в issue и не просто «проверка настроек».

1. Через поиск Windows открыть **«Create a restore point» / «Создание точки восстановления»** (`SystemPropertiesProtection.exe`). Для системного **C:** включить **System Protection**, если отключена.
2. **Настроить лимит VSS до создания первой точки:** целевой максимум — точно **12 GiB = 12 884 901 888 байт**. В GUI процент от текущего C: даёт лишь приближение; для точного лимита использовать штатный **CMD с повышенными правами**, без сценария или дополнительного ПО:

```cmd
vssadmin resize shadowstorage /for=C: /on=C: /maxsize=12884901888
vssadmin list shadowstorage
```

Это официальный синтаксис Microsoft: без суффикса единиц `/maxsize` задаётся **в байтах**. **Важно:** изменение размера shadow storage может удалить существующие shadow copies; на уже настроенной ASUS сперва проверить имеющиеся точки и не уменьшать хранилище без отдельной оценки. На чистой системе выполнить ограничение **до** первого checkpoint.
3. **Отключить 24-часовой пропуск новых точек** для последующих восстановительных checkpoint (штатный документированный механизм Windows). В том же CMD администратора, **до создания точки**, выполнить:

```cmd
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\SystemRestore" /v SystemRestorePointCreationFrequency /t REG_DWORD /d 0 /f
reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\SystemRestore" /v SystemRestorePointCreationFrequency
```

`SystemRestorePointCreationFrequency=0` выключает throttling для программного API создания точек; это **не** создаёт точку самостоятельно. Источник: [Microsoft SRSetRestorePoint](https://learn.microsoft.com/en-us/windows/win32/sr/calling-srsetrestorepoint), [Microsoft VSS storage](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/vssadmin-resize-shadowstorage).
4. Нажать **Create / Создать** в системном окне и дать однозначное имя с датой, например `WinOps - clean Windows - 2026-10-11` (для нового развёртывания подставить **дату фактического запуска**). Дождаться сообщения, что точка успешно создана. Если создание точки невозможно — **STOP**: не начинать наши настройки.
5. Проверить, что **именно новая** точка присутствует в **System Restore / Восстановление системы**, с правильной датой и именем. Зафиксировать **название, время и факт существования** точки в локальном отчёте и, при аппаратной приёмке, фактическом журнале [issue #9](https://github.com/evanmih-cmd/linux/issues/9). Не публиковать секреты.

Точка восстановления — **не полный offline backup**, не гарантия отката LGPO/TPM/BitLocker/UEFI и не замена отдельной внешней копии подготовленного WinRE. Она нужна как максимально ранний **штатный checkpoint неизменённой Windows**. Отдельный **полный образ системы на внешнем носителе делать лишь после полной настройки и стабилизации рабочей станции** (согласованное требование). Перед следующими крупными партиями изменений создавать новые restore points; не полагаться на стандартный дневной throttle как на подтверждение создания новой точки.

**Разрешение на этап 3:** доказаны рабочая штатная ОС после обновлений и существующая точка восстановления `WinOps - clean Windows ...`. Если checkpoint не создан, этап 3 не запускать.

## Этап 3. Наша конфигурация и hardening — только после checkpoint

**Канонический вход один**: `windows/configuration/workstation.winget` + штатный запуск Microsoft DSC из `windows/vm/payload/apply-configuration.ps1`. Скрипт последовательно выполняет официальный DSC, затем уже подготовленную Microsoft Security Baseline **26H2 v2 через штатный LGPO** с принятыми WinOps-исключениями. Нельзя запускать в обход один из stock-импортов Microsoft, который устанавливает `DeltaForNonDomainJoined`, либо применять `security-hardware.winget` на этом этапе.

**Подготовка:** USB `U:\PostInstall\` по [installation runbook](vm/deployment/README.md) содержит `workstation.winget`, `apply-configuration.ps1`, проверенный по SHA-256 официальный архив `DSC-3.3.0-x86_64-pc-windows-msvc.zip`, папку `security-baseline\` со всеми тремя конечными LGPO политическими файлами, `APPLY.CMD` и **официальным Microsoft** `security-baseline\Tools\LGPO.exe` из отдельного пакета SCT `LGPO.zip`. Четыре файла установленного аудитора `RUN-AUDIT.CMD`, `run-audit.ps1`, `audit.ps1`, `evaluate-audit.ps1` тоже находятся вместе на USB. **Если LGPO.exe нет**, запуск fail-closed; не считать релиз готовым «на словах». Интернет необходим для официального WinGet пакетов.

Войти под `owner`, открыть **Windows PowerShell с повышенными правами** (после проверки стандартного UAC/Hello), определить букву USB и выполнить:

```powershell
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "U:\PostInstall\apply-configuration.ps1" -ConfigurationPath "U:\PostInstall\workstation.winget"
```

**Внутри одного запуска:**

- **DSC/WinGet** — официальные PowerShell, Chrome (основной защищённый профиль), Edge (обычные задачи), KeePass 2, Ledger Wallet; расширения Chrome по официальной Enterprise `ExtensionSettings` политике; Administrator Protection, политика BitLocker TPM+PIN (сама по себе **не enroll** PIN/protectors), VBS/HVCI и возможность запуска Windows Sandbox.
- **LGPO** — Microsoft Security Baseline 26H2 v2 в версии WinOps (330 реестровых политик, security template, 23 subcategories auditing). Сохраняются secure-desktop credentials, запреты local-account remote logon, Defender cloud с **запросом согласия на образцы**, запись на незашифрованные USB разрешена, **без UEFI-lock** и без доменной LAPS.
- **После запуска** — `C:\ProgramData\DesktopWindows\configuration.log` должен содержать **`DSC exit=0`**, **`LGPO exit=0`**, **`BASELINE=PASS`**, **`CONFIGURATION=PASS`**. Эти строки свидетельствуют о завершении вызовов, **не** гарантируют функциональность защищённых подсистем.

**Далее — специфические штатные действия, которые пока НЕ реализованы декларативным DSC:**

- Перезагрузиться **по решению владельца** после успешного DSC/LGPO, завершить Windows `Customizing features` и проверить реальные Windows Hello Face/PIN и **Administrator Protection**: новая защищённая `ADMIN_owner` + явная авторизация, а не обычный Yes/No UAC. На ASUS от 2026-10-11 ранее был подтверждён **реальный FAIL ShadowAdmin при policy=2**. Не объявлять его исправленным из-за LGPO/registry read-back; до действительной работы механизм не принят. Не применять недокументированные FeatureManagement/ViveTool overrides ради искусственного PASS.
- Windows Update policy — стабильные security/quality updates штатно; без принудительного автоматического firmware update/feature upgrade, удерживать **26H2**. Не создавать самодельный блокировщик перезагрузок. Отключить OneDrive и нежелательную синхронизацию, **историю** и межустройственную синхронизацию буфера (обычный clipboard сохранить). Диагностика — `Required data only`.
- G-Helper на ASUS — отдельно, официальная версия и источник; цель charge limit **60%**, поддержка самого лимита доказывается фактическим hardware readback. Разрешённая архитектура: one-shot запуск от SYSTEM для установки аппаратного лимита и unelevated пользовательский GUI ради Fn/аппаратных органов. Не включать дополнительные WinRing драйверы; не отключать критические службы ASUS «на всякий случай». Это **отдельное внедрение**, не считать наличие `workstation.winget` автоматическим выполнением всех этих операций.
- Восстановление: System Protection/restore points уже должны быть включены с checkpoint этапа 2; не заменять их непрозрачным собственным backup tool; перед последующими крупными изменениями дополнительные restore points по необходимости.
- Windows Sandbox: создать штатную папку `C:\Sandbox-Inbox` без секретов/кошельков/баз; использовать **два разных** файла `sandbox-untrusted.wsb` (полностью offline) и `sandbox-networked.wsb` (Internet + LAN), **clipboard включён в обоих**; host folder read-only. `ProtectedClient` может ограничивать передачу файлов через clipboard. Networked mode имеет доступ к LAN и **не подходит для вредоносного кода, который должен быть изолирован от локальной сети**.
- Вручную впервые запустить Chrome под `owner`, завершить начальные окна, проверить `chrome://policy` → `ExtensionSettings: OK` и наличие/включение шести расширений (MetaMask, Phantom, Rabby, Trust Wallet, Backpack, Zerion) в `chrome://extensions`. Никаких seed phrases при установке. KeePass/Ledger использовать только с проверенным официальным ПО; реальную аппаратную подпись и доступные USB-токены принимать отдельно.
- BitLocker: подтвердить `C:` Protection On, TPM **+ Startup PIN** (не TPM-only bypass), отдельный recovery protector, наличие проверенной **офлайн** копии recovery key. Если защита ещё не была правильно настроена — это отдельное штатное BitLocker enrollment действие владельца; политики DSC **не эквивалентны** фактическому enroll. Не выводить recovery key в сохраняемые логи. Recovery-раздел должен оставаться fully decrypted, а системный C: — защищённым.

**UEFI-lock не запускать.** `windows/configuration/security-hardware.winget` — отдельный намеренно сохранённый optional overlay. Решение о нём возвращается **только после** нормальной настройки, совместимости драйверов и положительной аппаратной приёмки.

## Этап 4. Итоговая приёмка — отдельно от применения политик

Запустить **установленный** аудит `U:\PostInstall\RUN-AUDIT.CMD` (это **не** WinPE `AUDIT.CMD`). Открыть и сохранить:

```text
C:\ProgramData\DesktopWindows\Audit\report.txt
C:\ProgramData\DesktopWindows\Audit\result.json
C:\ProgramData\DesktopWindows\Audit\facts.json
```

Проверить **функционально**: повторную нормальную загрузку по TPM+PIN, Hello Face/ESS + PIN, подтверждение администрирования через защищённый desktop/ShadowAdmin, Device Guard/HVCI и Defender *running*, обе Sandbox с правильными сетевыми режимами и clipboard, Windows Update, лицензирование/драйверы и отсутствие незапланированного ASUS OEM автософта. Отдельно подтвердить независимость загрузки WinHome/SSD1, что фактически загружается WinRE и видит AMD RAID LUN, восстановление по офлайн recovery key в предусмотренной контролируемой процедуре, физический Ledger path. Показать реальные `FAIL/NOT_PROVABLE`; ни registry setting, ни успешный DSC/Linux VM benchmark не являются доказательством физической работы.

**Только после полноценного рабочего и проверенного результата** — внешний **полный offline образ системы**, независимо от временных точек System Restore. Отдельно сохранить подготовленный WinRE-образ и контрольную сумму вне WinOps RAID LUN, как требует [installation runbook](vm/deployment/README.md). Hardware результаты записывать в замороженный append-only журнал [issue #9](https://github.com/evanmih-cmd/linux/issues/9); план/изменения конфигурации — в [issue #5](https://github.com/evanmih-cmd/linux/issues/5).

## Границы

- **Не путать** Stage 2 Windows restore point с Git checkpoint или образом системы.
- **Не запускать** DSC/LGPO на неготовой Windows; не маскировать невыполненную штатную установку/Windows Update под «процент PASS» скрипта.
- **Не повторять** на уже установленном ASUS ручную разметку, WinPE RAID integration, `DISM /Apply-Image` и `reagentc` без отдельной задачи восстановления.
- **Не внедрять** пользовательские постоянные агенты, собственный движок hardening, обходы Windows Update или скрытый тестовый/prod профиль.

Связанные исходники: [installation/deployment runbook](vm/deployment/README.md), [DSC desired state](configuration/workstation.winget), [Microsoft LGPO baseline](configuration/security-baseline/README.md), [installed Windows audit](vm/payload/README-AUDIT.md), [accepted architecture](ARCHITECTURE.md), [ASUS hardware observations](https://github.com/evanmih-cmd/linux/issues/9).
