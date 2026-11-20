$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$jdkBin = (Get-ChildItem '.tools\jdk' -Filter javac.exe -Recurse | Select-Object -First 1).Directory.FullName
$buildTools = (Get-ChildItem '.tools\build-tools' -Filter aapt2.exe -Recurse | Select-Object -First 1).Directory.FullName
$androidJar = (Get-ChildItem '.tools\platform' -Filter android.jar -Recurse | Select-Object -First 1).FullName
if (!$jdkBin -or !$buildTools -or !$androidJar) { throw 'Run python bootstrap_android.py first.' }
$env:JAVA_HOME = Split-Path $jdkBin
$env:PATH = "$jdkBin;$env:PATH"
New-Item -ItemType Directory -Force 'build\android\classes','build\android\dex','dist' | Out-Null
$classesDir = Join-Path 'build\android' ('classes-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force $classesDir | Out-Null
function Check-Result { if ($LASTEXITCODE -ne 0) { throw "Build tool failed: $LASTEXITCODE" } }
$javaSources = @(Get-ChildItem android\app\src\main\java -Filter *.java -Recurse | ForEach-Object FullName)
& "$jdkBin\javac.exe" -encoding UTF-8 --release 8 -classpath $androidJar -d $classesDir $javaSources
Check-Result
& "$jdkBin\jar.exe" cf build\android\classes.jar -C $classesDir .
Check-Result
& "$buildTools\d8.bat" --lib $androidJar --min-api 26 --output build\android\dex build\android\classes.jar
Check-Result
$manifest = (Get-Content android\app\src\main\AndroidManifest.xml -Raw).Replace('<manifest ', '<manifest package="cn.lanremote" ')
[System.IO.File]::WriteAllText("$PSScriptRoot\build\android\AndroidManifest.xml", $manifest, [System.Text.UTF8Encoding]::new($false))
& "$buildTools\aapt2.exe" link -o build\android\unsigned.apk -I $androidJar --manifest build\android\AndroidManifest.xml --min-sdk-version 26 --target-sdk-version 35 --version-code 3 --version-name 0.2.0
Check-Result
& "$jdkBin\jar.exe" uf build\android\unsigned.apk -C build\android\dex classes.dex
Check-Result
& "$buildTools\zipalign.exe" -f 4 build\android\unsigned.apk build\android\aligned.apk
Check-Result
if (!(Test-Path '.tools\development.jks')) {
    & "$jdkBin\keytool.exe" -genkeypair -keystore .tools\development.jks -storepass android -keypass android -alias lanremote -keyalg RSA -keysize 2048 -validity 3650 -dname 'CN=LanRemote Development'
    Check-Result
}
& "$buildTools\apksigner.bat" sign --ks .tools\development.jks --ks-key-alias lanremote --ks-pass pass:android --key-pass pass:android --out dist\LanRemote-Android.apk build\android\aligned.apk
Check-Result
& "$buildTools\apksigner.bat" verify --verbose dist\LanRemote-Android.apk
Check-Result
