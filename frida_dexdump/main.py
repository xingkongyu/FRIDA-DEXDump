# Author: hluwa <hluwa888@gmail.com>
# HomePage: https://github.com/hluwa
# CreatedTime: 2020/1/7 20:57
import hashlib
import os
import random
import sys
import getopt
import time
import frida
import logging
import traceback

try:
    from shutil import get_terminal_size as get_terminal_size
except:
    try:
        from backports.shutil_get_terminal_size import get_terminal_size as get_terminal_size
    except:
        pass
try:
    import click
except:
    class click:

        @staticmethod
        def secho(message=None, **kwargs):
            print(message)

        @staticmethod
        def style(**kwargs):
            raise Exception("unsupported style")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s",
                    datefmt='%m-%d/%H:%M:%S')

banner = """
----------------------------------------------------------------------------------------
  ____________ ___________  ___        ______ _______   _______                         
  |  ___| ___ \_   _|  _  \/ _ \       |  _  \  ___\ \ / /  _  \                        
  | |_  | |_/ / | | | | | / /_\ \______| | | | |__  \ V /| | | |_   _ _ __ ___  _ __    
  |  _| |    /  | | | | | |  _  |______| | | |  __| /   \| | | | | | | '_ ` _ \| '_ \   
  | |   | |\ \ _| |_| |/ /| | | |      | |/ /| |___/ /^\ \ |/ /| |_| | | | | | | |_) |  
  \_|   \_| \_|\___/|___/ \_| |_/      |___/ \____/\/   \/___/  \__,_|_| |_| |_| .__/   
                                                                               | |      
                                                                               |_|      
                      https://github.com/hluwa/FRIDA-DEXDump                            
----------------------------------------------------------------------------------------\n
"""

md5 = lambda bs: hashlib.md5(bs).hexdigest()


def show_banner():
    colors = ['bright_red', 'bright_green', 'bright_blue', 'cyan', 'magenta']
    try:
        click.style('color test', fg='bright_red')
    except:
        colors = ['red', 'green', 'blue', 'cyan', 'magenta']
    try:
        columns = get_terminal_size().columns
        if columns >= len(banner.splitlines()[1]):
            for line in banner.splitlines():
                if line:
                    fill = int((columns - len(line)) / 2)
                    line = line[0] * fill + line
                    line += line[-1] * fill
                click.secho(line, fg=random.choice(colors))
    except:
        pass


def get_all_process(device, pkgname):
    return [process for process in device.enumerate_processes() if pkgname in process.name]


def search(api):
    """
    """

    matches = api.scandex()
    for info in matches:
        click.secho("[DEXDump] Found: DexAddr={}, DexSize={}"
                    .format(info['addr'], hex(info['size'])), fg='green')
    return matches


def dump(pkg_name, api, mds=None):
    """
    """
    if mds is None:
        mds = []
    matches = api.scandex()
    for info in matches:
        try:
            bs = api.memorydump(info['addr'], info['size'])
            md = md5(bs)
            if md in mds:
                click.secho("[DEXDump]: Skip duplicate dex {}<{}>".format(info['addr'], md), fg="blue")
                continue
            mds.append(md)
            if not os.path.exists("./" + pkg_name + "/"):
                os.mkdir("./" + pkg_name + "/")
            if bs[:4] != b"dex\n":
                bs = b"dex\n035\x00" + bs[8:]
            with open(pkg_name + "/" + info['addr'] + ".dex", 'wb') as out:
                out.write(bs)
            click.secho("[DEXDump]: DexSize={}, DexMd5={}, SavePath={}/{}/{}.dex"
                        .format(hex(info['size']), md, os.getcwd(), pkg_name, info['addr']), fg='green')
        except Exception as e:
            click.secho("[Except] - {}: {}".format(e, info), bg='yellow')


def stop_other(pid, processes):
    try:
        for process in processes:
            if process.pid == pid:
                os.system("adb shell \"su -c 'kill -18 {}'\"".format(process.pid))
            else:
                os.system("adb shell \"su -c 'kill -19 {}'\"".format(process.pid))
    except:
        pass


def choose(pid=None, pkg=None, spawn=False, device=None):
    if pid is None and pkg is None:
        target = device.get_frontmost_application()
        return target.pid, target.identifier

    for process in device.enumerate_processes():
        if (pid and process.pid == pid) or (pkg and process.name == pkg):
            if not spawn:
                return process.pid, process.name
            else:
                pkg = process.name
                break

    if pkg and spawn and device:
        pid = device.spawn(pkg)
        device.resume(pid)
        return pid, pkg
    raise Exception("Cannot found <{}> process".format(pid))


def show_help():
    help_str = "Usage: frida-dexdump -n <process> -p <pid> -f[enable spawn mode] -s <delay seconds> -d[enable deep search]\n\n" \
               "    -n: [Optional] Specify target process name, when spawn mode, it requires an application package name. If not specified, use frontmost application.\n" \
               "    -p: [Optional] Specify pid when multiprocess. If not specified, dump all.\n" \
               "    -f: [Optional] Use spawn mode, default is disable.\n" \
               "    -s: [Optional] When spawn mode, start dump work after sleep few seconds. default is 10s.\n" \
               "    -d: [Optional] Enable deep search maybe detected more dex, but speed will be slower.\n" \
               "    -h: show help.\n"
    print(help_str)


def connect_device():
    try:
        device = frida.get_usb_device()
    except:
        device = frida.get_remote_device()

    return device


def entry():
    show_banner()

    process = None
    pid = None
    enable_spawn_mode = False
    delay_second = 10
    enable_deep_search = False

    try:
        opts, args = getopt.getopt(sys.argv[1:], "hn:p:fs:d")

        def arg2int(v):
            try:
                return int(v)
            except:
                return int(v.replace('0x', ''), 16)

        for arg, value in opts:
            if arg == '-n':
                process = value
            elif arg == '-p':
                pid = arg2int(value)
            elif arg == '-f':
                enable_spawn_mode = True
            elif arg == '-s':
                delay_second = arg2int(value)
            elif arg == "-d":
                enable_deep_search = True
            elif arg == '-h':
                show_help()
                exit(0)

    except getopt.GetoptError:
        show_help()
        exit(2)

    if enable_spawn_mode and pid is not None:
        pid = None

    def forward_frida():
        os.system("adb forward tcp:27042 tcp:27042")
        os.system("adb forward tcp:27043 tcp:27043")

    try:
        device = connect_device()
        if not device:
            raise Exception("Unable to connect.")
    except:
        forward_frida()
        device = connect_device()

    if not device:
        click.secho("[Except] - Unable to connect to device.", bg='red')
        exit()

    pname = None
    try:
        _, pname = choose(device=device, pkg=process, pid=pid, spawn=enable_spawn_mode)
        if enable_spawn_mode:
            logging.info("[DEXDump]: sleep {}s".format(delay_second))
            time.sleep(delay_second)
    except Exception as e:
        click.secho("[Except] - Unable to inject into process: {} in \n{}".format(e, traceback.format_tb(
            sys.exc_info()[2])[-1]), bg='red')
        exit()

    processes = get_all_process(device, pname)
    mds = []
    for process in processes:

        if pid is not None and process.pid != pid:
            continue

        logging.info("[DEXDump]: found target [{}] {}".format(process.pid, process.name))
        stop_other(process.pid, processes)
        session = device.attach(process.pid)
        path = os.path.dirname(__file__)
        script = session.create_script(open(os.path.join(path, "agent.js")).read())
        script.load()
        if enable_deep_search:
            script.exports.switchmode(True)
            logging.info("[DEXDump]: deep search mode is enable, may wait some time.")
        dump(pname, script.exports, mds=mds)
        script.unload()
        session.detach()
    exit()


if __name__ == "__main__":
    entry()
