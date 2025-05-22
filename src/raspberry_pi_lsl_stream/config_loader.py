"""Configuration loader for Raspberry Pi Camera Capture."""

import os
import yaml
import argparse
from typing import Dict, Any, Optional

def load_config(config_path: str = 'config.yaml') -> Dict[str, Any]:
    """
    Load configuration from YAML file.
    
    Args:
        config_path: Path to the configuration file
        
    Returns:
        Dictionary with configuration values
    """
    # Default configuration
    default_config = {
        'camera': {
            'width': 400,
            'height': 400,
            'fps': 100,
            'codec': 'mjpg',
            'container': 'mkv',
            'preview': False,
            'enable_crop': 'auto',
        },
        'storage': {
            'save_video': True,
            'output_dir': 'recordings',
            'create_date_folders': True,
        },
        'buffer': {
            'size': 20.0,
            'enabled': True,
        },
        'remote': {
            'ntfy_topic': 'raspie-camera-test',
        },
        'lsl': {
            'stream_name': 'VideoStream',
        },
        'performance': {
            'capture_cpu_core': None,
            'writer_cpu_core': None,
            'lsl_cpu_core': None,
            'ntfy_cpu_core': None,
        },
        'audio': {
            'sample_rate': 44100,
            'channels': 1,
            'bit_depth': 16,
            'save_audio': True,
            'audio_format': 'wav',
            'show_preview': False,
        }
    }
    
    # Load from file if it exists
    config = default_config.copy()
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                file_config = yaml.safe_load(f)
                
            # Update default config with file config
            if file_config:
                for section, values in file_config.items():
                    if section in config and isinstance(values, dict):
                        config[section].update(values)
                    else:
                        config[section] = values
                        
            print(f"Loaded configuration from {config_path}")
        except Exception as e:
            print(f"Error loading configuration from {config_path}: {e}")
            print("Using default configuration")
    else:
        print(f"Configuration file {config_path} not found, using default settings")
        
    return config

def merge_config_with_args(config: Dict[str, Any], args: Optional[argparse.Namespace] = None) -> Dict[str, Any]:
    """
    Merge configuration with command-line arguments.
    Command-line arguments take precedence over configuration file.
    
    Args:
        config: Configuration dictionary
        args: Parsed command-line arguments
        
    Returns:
        Updated configuration dictionary
    """
    if args is None:
        return config
        
    merged_config = config.copy()
    
    # Camera settings
    camera_config = merged_config.get('camera', {})
    if hasattr(args, 'width') and args.width is not None:
        camera_config['width'] = args.width
    if hasattr(args, 'height') and args.height is not None:
        camera_config['height'] = args.height
    if hasattr(args, 'fps') and args.fps is not None:
        camera_config['fps'] = args.fps
    if hasattr(args, 'codec') and args.codec is not None:
        camera_config['codec'] = args.codec
    if hasattr(args, 'container') and args.container is not None:
        camera_config['container'] = args.container
    if hasattr(args, 'preview') and args.preview is not None:
        camera_config['preview'] = args.preview
    if hasattr(args, 'enable_crop') and args.enable_crop is not None:
        camera_config['enable_crop'] = args.enable_crop
    merged_config['camera'] = camera_config
    
    # Storage settings
    storage_config = merged_config.get('storage', {})
    if hasattr(args, 'save_video'):
        storage_config['save_video'] = args.save_video
    if hasattr(args, 'output_dir') and args.output_dir is not None:
        storage_config['output_dir'] = args.output_dir
    merged_config['storage'] = storage_config
    
    # Buffer settings
    buffer_config = merged_config.get('buffer', {})
    if hasattr(args, 'buffer_size') and args.buffer_size is not None:
        buffer_config['size'] = args.buffer_size
    if hasattr(args, 'no_buffer'):
        buffer_config['enabled'] = not args.no_buffer
    merged_config['buffer'] = buffer_config
    
    # Remote control settings
    remote_config = merged_config.get('remote', {})
    if hasattr(args, 'ntfy_topic') and args.ntfy_topic is not None:
        remote_config['ntfy_topic'] = args.ntfy_topic
    merged_config['remote'] = remote_config
    
    # LSL settings
    lsl_config = merged_config.get('lsl', {})
    if hasattr(args, 'stream_name') and args.stream_name is not None:
        lsl_config['stream_name'] = args.stream_name
    merged_config['lsl'] = lsl_config
    
    # Performance settings
    performance_config = merged_config.get('performance', {})
    if hasattr(args, 'capture_cpu_core') and args.capture_cpu_core is not None:
        performance_config['capture_cpu_core'] = args.capture_cpu_core
    if hasattr(args, 'writer_cpu_core') and args.writer_cpu_core is not None:
        performance_config['writer_cpu_core'] = args.writer_cpu_core
    if hasattr(args, 'lsl_cpu_core') and args.lsl_cpu_core is not None:
        performance_config['lsl_cpu_core'] = args.lsl_cpu_core
    if hasattr(args, 'ntfy_cpu_core') and args.ntfy_cpu_core is not None:
        performance_config['ntfy_cpu_core'] = args.ntfy_cpu_core
    merged_config['performance'] = performance_config
    
    return merged_config

def get_camera_config(config_path: str = 'config.yaml', args: Optional[argparse.Namespace] = None) -> Dict[str, Any]:
    """
    Load configuration and merge with command-line arguments.
    
    Args:
        config_path: Path to the configuration file
        args: Parsed command-line arguments
        
    Returns:
        Final configuration dictionary
    """
    config = load_config(config_path)
    return merge_config_with_args(config, args) 