#!/usr/bin/env python3
# LSL Stream Direct Test
# By: Anzal KS <anzal.ks@gmail.com>
import time
import sys
import argparse

def test_lsl():
    """Test LSL stream creation and detection."""
    print("Testing LSL stream with numeric values...")
    
    try:
        import pylsl
        print(f"Using pylsl version: {pylsl.__version__}")
        
        # Find a compatible channel format
        channel_format = None
        for format_name in ['cf_float32', 'cf_float', 'cf_double', 'cf_double64']:
            if hasattr(pylsl, format_name):
                channel_format = getattr(pylsl, format_name)
                print(f"Using channel format: {format_name}")
                break
                
        if channel_format is None:
            print("ERROR: Could not find compatible LSL channel format")
            print("Available attributes:", dir(pylsl))
            return False
            
        # Create a test stream
        info = pylsl.StreamInfo(
            name="IMX296Camera",
            type="VideoEvents",
            channel_count=4,
            nominal_srate=100.0,
            channel_format=channel_format,
            source_id="test_script"
        )
        
        # Add metadata
        channels = info.desc().append_child("channels")
        channels.append_child("channel").append_child_value("label", "timestamp").append_child_value("unit", "s")
        channels.append_child("channel").append_child_value("label", "recording").append_child_value("unit", "bool")
        channels.append_child("channel").append_child_value("label", "frame").append_child_value("unit", "count")
        channels.append_child("channel").append_child_value("label", "trigger").append_child_value("unit", "id")
        
        # Create outlet
        outlet = pylsl.StreamOutlet(info)
        print(f"Created LSL stream: '{info.name()}' of type '{info.type()}'")
        
        # Push a test sample with guaranteed numeric values
        sample = [float(time.time()), 1.0, 0.0, 2.0]  # timestamp, recording, frame, trigger
        outlet.push_sample(sample)
        print(f"Pushed test sample: {sample}")
        
        # Check if we can find the stream
        print("Checking if stream is discoverable...")
        streams = pylsl.resolve_streams(2.0)
        found = False
        
        for stream in streams:
            if stream.name() == "IMX296Camera":
                found = True
                print(f"Found stream: {stream.name()}, type: {stream.type()}, channels: {stream.channel_count()}")
                
        if not found:
            print("WARNING: Stream was created but not discoverable")
            print("Available streams:")
            for s in streams:
                print(f"  - {s.name()} ({s.type()})")
            return False
            
        # Try to pull from the stream to check the full roundtrip
        print("Attempting to pull sample from stream...")
        inlets = pylsl.resolve_stream("name", "IMX296Camera")
        if len(inlets) == 0:
            print("ERROR: Could not resolve stream for inlet")
            return False
            
        inlet = pylsl.StreamInlet(inlets[0])
        inlet.open_stream()
        
        # Try to get a sample within timeout
        sample, timestamp = inlet.pull_sample(timeout=2.0)
        if sample is None:
            print("ERROR: Could not pull a sample from the stream")
            return False
            
        print(f"Received sample: {sample}, timestamp: {timestamp}")
        
        # All checks passed
        print("✓ LSL STREAM TEST PASSED")
        print("  - Created stream successfully")
        print("  - Pushed numeric sample")
        print("  - Stream is discoverable")
        print("  - Could pull sample from stream")
        return True
        
    except Exception as e:
        print(f"ERROR: LSL test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False
        
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test LSL stream creation and detection")
    parser.add_argument("--continuous", action="store_true", help="Run continuously, sending samples at regular intervals")
    parser.add_argument("--interval", type=float, default=1.0, help="Interval between samples when running continuously (seconds)")
    parser.add_argument("--duration", type=float, default=30.0, help="Duration to run in continuous mode (seconds)")
    args = parser.parse_args()
    
    if args.continuous:
        print(f"Running continuous LSL stream test for {args.duration} seconds")
        try:
            import pylsl
            
            # Find a compatible channel format
            channel_format = None
            for format_name in ['cf_float32', 'cf_float', 'cf_double', 'cf_double64']:
                if hasattr(pylsl, format_name):
                    channel_format = getattr(pylsl, format_name)
                    print(f"Using channel format: {format_name}")
                    break
                    
            if channel_format is None:
                print("ERROR: Could not find compatible LSL channel format")
                sys.exit(1)
                
            # Create a test stream
            info = pylsl.StreamInfo(
                name="IMX296Camera",
                type="VideoEvents",
                channel_count=4,
                nominal_srate=1.0 / args.interval,
                channel_format=channel_format,
                source_id="test_script_continuous"
            )
            
            # Create outlet
            outlet = pylsl.StreamOutlet(info)
            print(f"Created continuous LSL stream: '{info.name()}'")
            
            # Send samples until duration expires
            start_time = time.time()
            count = 0
            while time.time() - start_time < args.duration:
                sample = [float(time.time()), 1.0, float(count), 2.0]
                outlet.push_sample(sample)
                count += 1
                sys.stdout.write(f"\rPushed sample #{count}: {sample}")
                sys.stdout.flush()
                time.sleep(args.interval)
                
            print(f"\nContinuous test complete: sent {count} samples")
            sys.exit(0)
            
        except Exception as e:
            print(f"ERROR in continuous mode: {e}")
            sys.exit(1)
    else:
        # Run single test
        success = test_lsl()
        sys.exit(0 if success else 1) 