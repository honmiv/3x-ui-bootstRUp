# 3x-ui bootstRUp

* <img src="https://flagcdn.com/24x18/ru.png" width="24" alt="RU"> [Русская документация](https://honmiv.github.io/3x-ui-bootstRUp/ru/)
* <img src="https://flagcdn.com/24x18/gb.png" width="24" alt="EN"> [English documentation](https://honmiv.github.io/3x-ui-bootstRUp/en/)

---

## 🚀 Быстрый запуск графического Web UI мастера / Quick Web UI Launch

### 🐧 🍎 Linux / macOS (Bash / Zsh)
```bash
curl -fsSL https://github.com/honmiv/3x-ui-bootstRUp/archive/refs/heads/master.tar.gz | tar -xz && cd 3x-ui-bootstRUp-master && ./install.sh
```

### 💻 Windows CMD (cmd.exe)
```cmd
curl -fsSL https://github.com/honmiv/3x-ui-bootstRUp/archive/refs/heads/master.zip -o 3x-ui.zip && powershell -Command "Expand-Archive -Path '3x-ui.zip' -DestinationPath '.' -Force" && cd 3x-ui-bootstRUp-master && install.bat
```

### ⚡ Windows PowerShell
```powershell
cd ~; iwr -useb https://github.com/honmiv/3x-ui-bootstRUp/archive/refs/heads/master.zip -OutFile 3x-ui.zip; Expand-Archive 3x-ui.zip -DestinationPath . -Force; cd 3x-ui-bootstRUp-master; powershell -ExecutionPolicy Bypass -File .\install.ps1
```
