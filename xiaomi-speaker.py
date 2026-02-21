#!/usr/bin/env python3
"""
小爱音箱控制器 - 优雅版
支持：播放/暂停、音量调节、切歌、TTS语音播报
"""

import os
import sys
import json
import argparse
from pathlib import Path

# 配置文件路径
CONFIG_DIR = Path.home() / ".config" / "xiaomi-speaker"
DEVICE_CACHE = CONFIG_DIR / "devices.json"

def ensure_config_dir():
    """确保配置目录存在"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

def load_device_cache():
    """加载设备缓存"""
    if DEVICE_CACHE.exists():
        with open(DEVICE_CACHE, 'r') as f:
            return json.load(f)
    return {}

def save_device_cache(devices):
    """保存设备缓存"""
    ensure_config_dir()
    with open(DEVICE_CACHE, 'w') as f:
        json.dump(devices, f, indent=2, ensure_ascii=False)

def run_mijia_command(args_list):
    """运行 mijiaAPI 命令"""
    import subprocess
    cmd = [sys.executable, "-m", "mijiaAPI"] + args_list
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)

def check_login():
    """检查是否已登录"""
    auth_file = Path.home() / ".config" / "mijia-api" / "auth.json"
    return auth_file.exists()

def login():
    """执行登录流程"""
    print("🔐 未登录小米账号")
    print("📝 请在终端运行：")
    print()
    print(f"    python3 -m mijiaAPI --list_homes")
    print()
    print("📱 扫描显示的二维码，用米家 APP 完成登录")
    print("✅ 登录完成后，重新运行本脚本")
    return False

def get_devices(force_refresh=False):
    """获取设备列表，支持缓存"""
    if not force_refresh:
        cached = load_device_cache()
        if cached.get("devices"):
            print(f"📦 使用缓存的设备列表（{len(cached['devices'])} 个设备）")
            return cached["devices"]
    
    print("🔄 正在从云端获取设备列表...")
    success, stdout, stderr = run_mijia_command(["-l"])
    
    if not success:
        print(f"❌ 获取设备列表失败: {stderr}")
        return []
    
    devices = parse_devices(stdout)
    save_device_cache({"devices": devices})
    print(f"✅ 已获取 {len(devices)} 个设备并缓存")
    return devices

def parse_devices(output):
    """解析 mijiaAPI 输出，提取音箱设备"""
    devices = []
    lines = output.split('\n')
    current_device = None
    
    for line in lines:
        line = line.strip()
        if line.startswith('- '):
            if current_device and is_speaker_device(current_device):
                devices.append(current_device)
            device_name = line[2:].strip()
            current_device = {"name": device_name}
        elif 'did:' in line and current_device:
            current_device["did"] = line.split('did:')[1].strip()
        elif 'model:' in line and current_device:
            current_device["model"] = line.split('model:')[1].strip()
    
    if current_device and is_speaker_device(current_device):
        devices.append(current_device)
    
    return devices

def is_speaker_device(device):
    """判断是否为音箱设备"""
    speaker_keywords = ['speaker', 'sound', '音箱', '音响', '小爱', 'xiaomi.wifispeaker']
    name = device.get('name', '').lower()
    model = device.get('model', '').lower()
    return any(kw in name or kw in model for kw in speaker_keywords)

def find_device_by_name(devices, name_query):
    """根据名称查找设备"""
    name_query = name_query.lower()
    
    for device in devices:
        if name_query in device.get('name', '').lower():
            return device
    
    for device in devices:
        if any(part in device.get('name', '').lower() for part in name_query.split()):
            return device
    
    return None

def control_speaker(did, action, value=None):
    """控制音箱基础功能"""
    if action == 'volume':
        success, stdout, stderr = run_mijia_command([
            "set", "--did", did, "--prop_name", "volume", "--value", str(value)
        ])
    else:
        # 播放控制通过 action 接口
        action_map = {'play': 'play', 'pause': 'pause', 'next': 'next', 'prev': 'previous'}
        if action in action_map:
            success, stdout, stderr = run_mijia_command([
                "--run_scene", action_map[action]
            ])
        else:
            return False
    
    return success

def tts_speak(did, text):
    """TTS 语音播报"""
    try:
        from mijiaAPI import mijiaAPI
        api = mijiaAPI()
        result = api.run_action({
            'did': did,
            'siid': 5,
            'aiid': 1,
            'in': [text]
        })
        return result.get('code') == 0
    except Exception as e:
        print(f"❌ TTS 失败: {e}")
        return False

def get_speaker_status(did):
    """获取音箱状态"""
    success, stdout, stderr = run_mijia_command([
        "get", "--did", did, "--prop_name", "volume"
    ])
    return success, stdout

def main():
    parser = argparse.ArgumentParser(
        description='小爱音箱控制器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s list                    # 列出所有音箱
  %(prog)s play 小爱               # 播放
  %(prog)s pause 小爱              # 暂停
  %(prog)s volume 小爱 50          # 设置音量50%
  %(prog)s say 小爱 "该起床啦"     # TTS播报
  %(prog)s status 小爱             # 查看状态
        """
    )
    
    parser.add_argument('action', choices=[
        'list', 'play', 'pause', 'stop', 'next', 'prev', 'volume', 'say', 'status', 'refresh'
    ], help='操作类型')
    parser.add_argument('device', nargs='?', help='设备名称（如：小爱、客厅音箱）')
    parser.add_argument('value', nargs='?', help='音量值(0-100)或TTS文本')
    
    args = parser.parse_args()
    
    # 检查登录状态
    if not check_login():
        if not login():
            sys.exit(1)
    
    if args.action == 'refresh':
        get_devices(force_refresh=True)
        return
    
    if args.action == 'list':
        devices = get_devices()
        if not devices:
            print("❌ 未找到音箱设备")
            print("💡 尝试运行: %(prog)s refresh")
            return
        
        print(f"\n🎵 找到 {len(devices)} 个音箱设备:\n")
        for i, device in enumerate(devices, 1):
            print(f"  {i}. {device.get('name', 'Unknown')} ({device.get('model', 'Unknown')})")
            print(f"     DID: {device.get('did', 'N/A')[:20]}...")
        print()
        return
    
    if not args.device:
        print("❌ 请指定设备名称")
        print("💡 先用 %(prog)s list 查看可用设备")
        sys.exit(1)
    
    # 获取设备
    devices = get_devices()
    device = find_device_by_name(devices, args.device)
    
    if not device:
        print(f"❌ 未找到设备: {args.device}")
        print("💡 可用设备:")
        for d in devices:
            print(f"   - {d.get('name', 'Unknown')}")
        sys.exit(1)
    
    print(f"🎯 找到设备: {device['name']}")
    did = device['did']
    
    # 执行操作
    if args.action in ['play', 'pause', 'stop', 'next', 'prev']:
        if control_speaker(did, args.action):
            print(f"✅ {args.action} 成功")
    elif args.action == 'volume':
        if args.value is None:
            print("❌ 请指定音量值，例如: %(prog)s volume 小爱 50")
            sys.exit(1)
        try:
            vol = int(args.value)
            if not 0 <= vol <= 100:
                raise ValueError
            if control_speaker(did, 'volume', vol):
                print(f"✅ 音量已设置为 {vol}%")
        except ValueError:
            print("❌ 音量值需在 0-100 之间")
            sys.exit(1)
    elif args.action == 'say':
        if args.value is None:
            print('❌ 请指定播报内容，例如: %(prog)s say 小爱 "该起床啦"')
            sys.exit(1)
        if tts_speak(did, args.value):
            print(f'✅ 已播报: "{args.value}"')
    elif args.action == 'status':
        success, output = get_speaker_status(did)
        if success:
            print(f"📊 {output}")

if __name__ == '__main__':
    main()
