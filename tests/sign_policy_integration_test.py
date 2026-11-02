"""Build and run the private sign fixture, restoring production data/host.

Reserve title-host and web intermediates with concurrent workers first.
Run through build-queue; --native and --web can reserve separate windows.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
from sign_policy_fixture import ROOT, write

WORK = ROOT/'work/sign-policy'
HOST = ROOT/'build/tests/title-host/jungle'


def run(*args):
    subprocess.run([str(a) for a in args], cwd=ROOT, check=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native',action='store_true')
    parser.add_argument('--web',action='store_true')
    parser.add_argument('--toolchain',type=Path)
    parser.add_argument('--kryon',type=Path)
    parser.add_argument('--mingcute',type=Path)
    args=parser.parse_args()
    if not (args.native or args.web):args.native=args.web=True
    packages={name:path.resolve() for name,path in (
        ('ziran',args.toolchain),('kryon',args.kryon),('mingcute',args.mingcute)) if path}
    make_paths=[name+'='+str(packages[pkg]) for name,pkg in (
        ('TOOLCHAIN','ziran'),('KRYON','kryon'),('MINGCUTE','mingcute')) if pkg in packages]
    WORK.mkdir(parents=True,exist_ok=True)
    generated=ROOT/'host/jungle_title_data.zi'
    original=generated.read_bytes()
    (WORK/'production-title-data.zi').write_bytes(original)
    if args.native:
        shutil.copy2(HOST,WORK/'normal-title-host')
    try:
        generated.write_text(write(WORK))
        for testing in (False,True):
            if args.native:
                run('make','APP=build/tests/title-host','TEST_ROOMS='+str(int(testing)),*make_paths,
                    'build/tests/title-host/jungle')
                run(sys.executable,'tests/sign_policy_ui_test.py',*(['--testing'] if testing else []))
            if args.web:
                destination=WORK/('web-testing' if testing else 'web-release')
                import build_web
                package=build_web.package
                build_web.package=lambda name:packages[name] if name in packages else package(name)
                try:build_web.build(destination,test_rooms=testing)
                finally:build_web.package=package
                run(sys.executable,'tests/sign_policy_web_test.py','--web-root',destination,*(['--testing'] if testing else []))
    finally:
        generated.write_bytes(original)
        if args.native:
            shutil.copy2(WORK/'normal-title-host',HOST)
            (HOST.parent/'title-policy').write_text('0\n')
    run(sys.executable,'tools/title_scenes.py','--check')
    print('local sign integration passed; production title data restored'+('; private normal host restored' if args.native else ''),flush=True)


if __name__=='__main__':main()
