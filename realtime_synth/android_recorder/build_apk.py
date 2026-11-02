"""Standalone test APK build (SDK 35 / Build Tools 35.0.0, JDK 17+). No network needed."""
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'src/main'
JAVA = os.environ.get('JAVA_HOME') or 'E:/PyCharm_2026.1/jbr'
SDK = Path(os.environ.get('ANDROID_SDK_ROOT') or os.environ.get('ANDROID_HOME') or ROOT.parents[1] / 'tmp/android_recorder_sdk')
TOOLS = SDK / 'build-tools/35.0.0'
if not TOOLS.is_dir():
    TOOLS = SDK / 'build-tools/android-15'
ANDROID = SDK / 'platforms/android-35/android.jar'
KEYDIR = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'TangRecorder'
KEY = KEYDIR / 'test-signing.p12'
OUT = ROOT / 'dist/TangRecorder-1.3.apk'

def java(name):
    return str(Path(JAVA) / 'bin' / (name + ('.exe' if os.name=='nt' else '')))
def sdk(name):
    return str(TOOLS / (name + ('.exe' if os.name=='nt' else '')))
def run(*args):
    subprocess.run([str(a) for a in args],check=True)

def main():
    if not ANDROID.is_file():raise SystemExit('Set ANDROID_SDK_ROOT to an SDK with platform android-35.')
    OUT.parent.mkdir(exist_ok=True)
    KEYDIR.mkdir(parents=True,exist_ok=True)
    if not KEY.is_file():
        run(java('keytool'),'-genkeypair','-storetype','PKCS12','-keystore',KEY,'-storepass','android',
            '-keypass','android','-alias','tang-test','-keyalg','RSA','-keysize','2048','-validity','10000',
            '-dname','CN=Tang Recorder Development')
    with tempfile.TemporaryDirectory(prefix='tang-apk-') as tmp:
        b=Path(tmp);classes=b/'classes';classes.mkdir();dex=b/'dex';dex.mkdir()
        manifest=b/'AndroidManifest.xml'
        manifest.write_text((SRC/'AndroidManifest.xml').read_text(encoding='utf8').replace('<manifest ','<manifest package="cn.tangsynth.recorder" ',1),encoding='utf8')
        run(sdk('aapt2'),'compile','--dir',SRC/'res','-o',b/'res.zip')
        run(sdk('aapt2'),'link','-o',b/'app.apk','-I',ANDROID,'--manifest',manifest,
            '--min-sdk-version','23','--target-sdk-version','35','--version-code','4','--version-name','1.3',
            '-A',SRC/'assets',b/'res.zip')
        boot_classpath=os.pathsep.join((str(TOOLS/'core-lambda-stubs.jar'),str(ANDROID)))
        run(java('javac'),'-encoding','UTF-8','-source','8','-target','8','-bootclasspath',boot_classpath,
            '-d',classes,*sorted((SRC/'java').rglob('*.java')))
        with zipfile.ZipFile(b/'classes.jar','w') as jar:
            for f in classes.rglob('*.class'):jar.write(f,f.relative_to(classes).as_posix())
        run(java('java'),'-cp',TOOLS/'lib/d8.jar','com.android.tools.r8.D8','--min-api','23',
            '--lib',ANDROID,'--output',dex,b/'classes.jar')
        with zipfile.ZipFile(b/'app.apk','a') as apk:apk.write(dex/'classes.dex','classes.dex')
        run(sdk('zipalign'),'-f','4',b/'app.apk',b/'aligned.apk')
        sign=[java('java'),'-jar',TOOLS/'lib/apksigner.jar']
        run(*sign,'sign','--ks',KEY,'--ks-key-alias','tang-test','--ks-pass','pass:android',
            '--key-pass','pass:android','--v4-signing-enabled','false','--out',b/'signed.apk',b/'aligned.apk')
        run(*sign,'verify','--verbose',b/'signed.apk')
        OUT.write_bytes((b/'signed.apk').read_bytes())
    print(OUT)
if __name__=='__main__':main()
