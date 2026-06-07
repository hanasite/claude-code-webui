Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = scriptDir
' 后台启动服务器
WshShell.Run "pythonw.exe server.py --no-browser", 0, False
' 等 3 秒让服务器就绪
WScript.Sleep 3000
' 打开浏览器
WshShell.Run "http://127.0.0.1:19876"
