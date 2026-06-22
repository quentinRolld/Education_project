#!/usr/bin/env python3
import pyaudio

def main():
    p = pyaudio.PyAudio()
    info = p.get_host_api_info_by_index(0)
    numdevices = info.get('deviceCount')
    
    print("\n=== PLAYBACK DEVICES (OUTPUT) ===")
    for i in range(0, numdevices):
        device_info = p.get_device_info_by_host_api_device_index(0, i)
        if device_info.get('maxOutputChannels') > 0:
            print(f"Index {i}: {device_info.get('name')} (Max Channels: {device_info.get('maxOutputChannels')})")

    print("\n=== CAPTURE DEVICES (INPUT) ===")
    for i in range(0, numdevices):
        device_info = p.get_device_info_by_host_api_device_index(0, i)
        if device_info.get('maxInputChannels') > 0:
            print(f"Index {i}: {device_info.get('name')} (Max Channels: {device_info.get('maxInputChannels')})")
            
    print("\n================================")
    p.terminate()

if __name__ == '__main__':
    main()
