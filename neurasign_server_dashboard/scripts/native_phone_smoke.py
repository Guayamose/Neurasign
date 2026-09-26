"""Actual Android APK acceptance. Local emulator and Firebase only; no sensor fixtures.
Requires an installed local-build APK and adb on PATH (or ANDROID_HOME).
"""
from pathlib import Path
import os
import re
import shlex
import subprocess
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlencode
from workspace_smoke import WEB, call, test_user

ROOT=Path(__file__).resolve().parents[1]
ADB=str(Path(os.environ.get('ANDROID_HOME',str(Path.home()/'Android/Sdk')))/'platform-tools/adb')
PACKAGE='com.neurasign.link'
ARTIFACTS=ROOT.parent/'neurasign_phone_app/mobile/artifacts'

def adb(*args):
    result=subprocess.run([ADB,*args],capture_output=True,timeout=25)
    assert result.returncode==0, f'adb {args[0]} failed'
    return result.stdout

def shell(*args): return adb('shell',shlex.join(args))

def tree():
    shell('uiautomator','dump','/sdcard/neurasign-test.xml')
    return ET.fromstring(shell('cat','/sdcard/neurasign-test.xml'))

def find(text):
    return next((node for node in tree().iter('node') if node.get('text','').casefold()==text.casefold() or node.get('content-desc','').casefold()==text.casefold()),None)

def visible(text, timeout=25):
    deadline=time.time()+timeout
    while time.time()<deadline:
        node=find(text)
        if node is not None: return node
        time.sleep(.4)
    raise AssertionError(f'Native text not visible: {text}')

def tap(text):
    node=visible(text);bounds=[int(v) for v in re.findall(r'\d+',node.get('bounds'))]
    if bounds[3] > 2200:
        shell('input','swipe','540','1950','540','1100','350')
        node=visible(text);bounds=[int(v) for v in re.findall(r'\d+',node.get('bounds'))]
    shell('input','tap',str((bounds[0]+bounds[2])//2),str((bounds[1]+bounds[3])//2))

def screenshot(name): (ARTIFACTS/name).write_bytes(adb('exec-out','screencap','-p'))

def launch(): shell('am','start','-n',PACKAGE+'/.MainActivity')

def main():
    assert call('GET','/config')['firebase']['projectId']=='demo-neurasign'
    assert shell('getprop','ro.kernel.qemu').strip()==b'1', 'Only Android emulators allowed.'
    ARTIFACTS.mkdir(exist_ok=True)
    # This resets only the application installed in our disposable test emulator.
    shell('pm','clear',PACKAGE)
    adb('reverse','tcp:3000','tcp:3000')
    adb('logcat','-c')
    launch();visible('Scan connection code');screenshot('android-connect.png')
    owner=test_user('NativeOwner')
    org=call('POST','/organizations',owner['token'],{'name':'Native app acceptance'},201)['id']
    base=f'/organizations/{org}'
    team=call('POST',base+'/teams',owner['token'],{'name':'Operations'},201)['id']
    person=call('POST',base+'/employees',owner['token'],{'name':'Alex Morgan','team_id':team},201)['id']
    token=call('POST',base+f'/employees/{person}/enrollments',owner['token'],{'source':'wearable'},201)['token']
    link='neurasign://enroll#'+urlencode({'server':WEB,'token':token})
    shell('am','start','-a','android.intent.action.VIEW','-d',link,PACKAGE)
    visible('Your connection.');visible('Native app acceptance');visible('Alex Morgan');screenshot('android-confirm.png')
    tap('Confirm & connect');visible('Your wearable link.');visible('Ready to connect')
    snapshot=call('GET',base+'/dashboard',owner['token'])
    assert len(snapshot['devices'])==1 and snapshot['members'][0]['sharing']
    assert not snapshot['members'][0]['signals'], 'No physiological data may be invented.'
    call('POST','/gateway/enrollment/preview',body={'token':token},expected=409)
    # Process death must recover the same secure enrollment without auto-starting.
    shell('am','force-stop',PACKAGE);launch();visible('Alex Morgan');visible('Ready to connect')
    assert len(call('GET',base+'/dashboard',owner['token'])['devices'])==1
    screenshot('android-status.png')
    # Keep BLE discovery truthful on an emulator; permission handling is native.
    for permission in ('BLUETOOTH_SCAN','BLUETOOTH_CONNECT','POST_NOTIFICATIONS'):
        shell('pm','grant',PACKAGE,'android.permission.'+permission)
    tap('Find wearable')
    time.sleep(2)
    assert not call('GET',base+'/dashboard',owner['token'])['members'][0]['signals']
    # An offline pause survives a process restart and reaches the real API later.
    adb('reverse','--remove','tcp:3000')
    tap('Pause sharing');visible('Paused on phone · waiting for server')
    shell('am','force-stop',PACKAGE);launch();visible('Paused on phone · waiting for server')
    adb('reverse','tcp:3000','tcp:3000');visible('Sharing paused',timeout=30)
    assert call('GET',base+'/dashboard',owner['token'])['members'][0]['sharing'] is False
    screenshot('android-paused.png')
    # Disconnect through the native confirmation dialog; server revocation follows.
    tap('Disconnect company');tap('Disconnect')
    visible('Scan connection code')
    assert not call('GET',base+'/dashboard',owner['token'])['devices']
    shell('am','force-stop',PACKAGE);launch();visible('Scan connection code')
    errors=adb('logcat','-d','-s','ReactNativeJS:E','AndroidRuntime:E').decode()
    assert 'Process: com.neurasign.link' not in errors and 'TypeError' not in errors, 'Native runtime error; inspect emulator logcat.'
    print('PASS: installed native Android APK, SQLCipher startup, real API link preview/consent, single-use claim, secure enrollment across process restart, BLE permissions/discovery without fabricated data, persisted offline pause/recovery, server revocation and disconnect. Physical BLE and optical QR scan remain unvalidated.')

if __name__=='__main__': main()
