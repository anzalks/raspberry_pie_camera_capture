#!/usr/bin/env python3
"""
Video analysis utility to summarize frame rates and interframe intervals.
"""

import os
import sys
import cv2
import numpy as np
import argparse
import glob
import datetime
import time
import matplotlib.pyplot as plt
from pathlib import Path

def calculate_frame_times(video_path):
    """
    Extracts frame timestamps and calculates interframe intervals.
    
    Args:
        video_path: Path to video file
        
    Returns:
        dict: Dictionary containing frame timestamps, intervals, and statistics
    """
    if not os.path.exists(video_path):
        print(f"Error: Video file not found: {video_path}", file=sys.stderr)
        return None
        
    cap = None
    frame_times = []
    start_time = time.time()
    
    try:
        # Open the video file
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"Error: Could not open video file: {video_path}", file=sys.stderr)
            return None
            
        # Get basic video properties
        fps_metadata = cap.get(cv2.CAP_PROP_FPS)
        frame_count_metadata = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        if frame_count_metadata <= 0:
            print(f"Warning: Video reports invalid frame count: {frame_count_metadata}")
            
        # Process each frame and record actual timestamps
        frame_idx = 0
        while True:
            ret, _ = cap.read()
            if not ret:
                break
                
            # Record the timestamp for this frame
            current_time = time.time()
            frame_times.append(current_time)
            
            frame_idx += 1
            if frame_idx % 100 == 0:
                print(f"Processing frame {frame_idx}/{frame_count_metadata if frame_count_metadata > 0 else '?'}", end='\r')
                
        # Calculate actual frame count
        actual_frame_count = len(frame_times)
        
        # Calculate interframe intervals
        if len(frame_times) > 1:
            frame_times = np.array(frame_times)
            intervals = np.diff(frame_times)
            
            # Calculate statistics
            avg_interval = np.mean(intervals)
            min_interval = np.min(intervals)
            max_interval = np.max(intervals)
            std_interval = np.std(intervals)
            actual_fps = 1.0 / avg_interval
            duration = frame_times[-1] - frame_times[0]
            
            # Calculate percentiles for interval distribution
            percentiles = {
                "1%": np.percentile(intervals, 1),
                "5%": np.percentile(intervals, 5),
                "25%": np.percentile(intervals, 25),
                "50%": np.percentile(intervals, 50),  # median
                "75%": np.percentile(intervals, 75),
                "95%": np.percentile(intervals, 95),
                "99%": np.percentile(intervals, 99)
            }
            
            # Detect frame drops (unusually large intervals)
            # Define as intervals > 2x the median interval
            median_interval = percentiles["50%"]
            dropped_frame_threshold = median_interval * 2.0
            probable_drops = intervals > dropped_frame_threshold
            drop_count = np.sum(probable_drops)
            
            return {
                "file_path": video_path,
                "resolution": f"{width}x{height}",
                "metadata_fps": fps_metadata,
                "metadata_frame_count": frame_count_metadata,
                "actual_frame_count": actual_frame_count,
                "duration_seconds": duration,
                "calculated_fps": actual_fps,
                "avg_interval": avg_interval,
                "min_interval": min_interval,
                "max_interval": max_interval,
                "std_interval": std_interval,
                "interval_percentiles": percentiles,
                "probable_frame_drops": drop_count,
                "intervals": intervals  # Raw intervals for plotting
            }
        else:
            print(f"Error: Unable to calculate intervals - not enough frames ({len(frame_times)})")
            return {
                "file_path": video_path,
                "resolution": f"{width}x{height}",
                "metadata_fps": fps_metadata,
                "metadata_frame_count": frame_count_metadata,
                "actual_frame_count": actual_frame_count,
                "duration_seconds": 0,
                "error": "Not enough frames to calculate intervals"
            }
            
    except Exception as e:
        print(f"Error analyzing video: {e}", file=sys.stderr)
        return None
    finally:
        if cap:
            cap.release()
        end_time = time.time()
        print(f"Analysis completed in {end_time - start_time:.2f} seconds")

def generate_report(analysis_results, output_dir=None):
    """
    Generates text and visual reports from video analysis results.
    
    Args:
        analysis_results: Dictionary of analysis results from calculate_frame_times
        output_dir: Directory to save report files (optional)
    """
    if not analysis_results:
        print("No valid analysis results to report.")
        return
        
    # Create output directory if specified
    report_path = None
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        video_name = os.path.basename(analysis_results["file_path"])
        base_name = os.path.splitext(video_name)[0]
        report_path = os.path.join(output_dir, f"{base_name}_analysis_{timestamp}")
        
    # Generate text report
    print("\n--- Video Analysis Report ---")
    print(f"File: {analysis_results['file_path']}")
    print(f"Resolution: {analysis_results['resolution']}")
    print(f"Metadata FPS: {analysis_results['metadata_fps']:.3f}")
    print(f"Calculated FPS: {analysis_results['calculated_fps']:.3f}")
    print(f"Metadata Frame Count: {analysis_results['metadata_frame_count']}")
    print(f"Actual Frame Count: {analysis_results['actual_frame_count']}")
    print(f"Video Duration: {analysis_results['duration_seconds']:.3f} seconds")
    
    # Only print interval statistics if they exist
    if "intervals" in analysis_results:
        print("\n--- Interframe Interval Statistics (seconds) ---")
        print(f"Average Interval: {analysis_results['avg_interval'] * 1000:.3f} ms")
        print(f"Min Interval: {analysis_results['min_interval'] * 1000:.3f} ms")
        print(f"Max Interval: {analysis_results['max_interval'] * 1000:.3f} ms")
        print(f"Std Deviation: {analysis_results['std_interval'] * 1000:.3f} ms")
        
        print("\n--- Interval Percentiles (milliseconds) ---")
        for percentile, value in analysis_results["interval_percentiles"].items():
            print(f"{percentile}: {value * 1000:.3f} ms")
            
        print(f"\nProbable Frame Drops: {analysis_results['probable_frame_drops']}")
        
        # Generate plots if intervals are available
        if report_path:
            # Plot 1: Histogram of interframe intervals
            plt.figure(figsize=(12, 6))
            plt.hist(analysis_results["intervals"] * 1000, bins=50, alpha=0.75, color='blue')
            plt.title('Histogram of Interframe Intervals')
            plt.xlabel('Interval (milliseconds)')
            plt.ylabel('Frequency')
            plt.grid(True, alpha=0.3)
            plt.savefig(f"{report_path}_histogram.png", dpi=150)
            
            # Plot 2: Interframe intervals over time
            plt.figure(figsize=(12, 6))
            plt.plot(range(len(analysis_results["intervals"])), 
                     analysis_results["intervals"] * 1000, 
                     'b-', alpha=0.5)
            plt.axhline(y=analysis_results["avg_interval"] * 1000, 
                       color='r', linestyle='-', label=f'Average: {analysis_results["avg_interval"] * 1000:.2f} ms')
            plt.title('Interframe Intervals Over Time')
            plt.xlabel('Frame Number')
            plt.ylabel('Interval (milliseconds)')
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.savefig(f"{report_path}_intervals.png", dpi=150)
            
            # Save numerical results as text file
            with open(f"{report_path}_summary.txt", 'w') as f:
                f.write("--- Video Analysis Report ---\n")
                f.write(f"File: {analysis_results['file_path']}\n")
                f.write(f"Resolution: {analysis_results['resolution']}\n")
                f.write(f"Metadata FPS: {analysis_results['metadata_fps']:.3f}\n")
                f.write(f"Calculated FPS: {analysis_results['calculated_fps']:.3f}\n")
                f.write(f"Metadata Frame Count: {analysis_results['metadata_frame_count']}\n")
                f.write(f"Actual Frame Count: {analysis_results['actual_frame_count']}\n")
                f.write(f"Video Duration: {analysis_results['duration_seconds']:.3f} seconds\n")
                f.write("\n--- Interframe Interval Statistics (seconds) ---\n")
                f.write(f"Average Interval: {analysis_results['avg_interval'] * 1000:.3f} ms\n")
                f.write(f"Min Interval: {analysis_results['min_interval'] * 1000:.3f} ms\n")
                f.write(f"Max Interval: {analysis_results['max_interval'] * 1000:.3f} ms\n")
                f.write(f"Std Deviation: {analysis_results['std_interval'] * 1000:.3f} ms\n")
                f.write("\n--- Interval Percentiles (milliseconds) ---\n")
                for percentile, value in analysis_results["interval_percentiles"].items():
                    f.write(f"{percentile}: {value * 1000:.3f} ms\n")
                f.write(f"\nProbable Frame Drops: {analysis_results['probable_frame_drops']}\n")
            
            print(f"\nPlots and report saved to {report_path}_*.png and {report_path}_summary.txt")

def analyze_directory(directory_path, output_dir=None):
    """
    Analyzes all video files in a directory.
    
    Args:
        directory_path: Path to directory containing video files
        output_dir: Directory to save analysis reports
    """
    if not os.path.isdir(directory_path):
        print(f"Error: {directory_path} is not a valid directory", file=sys.stderr)
        return
        
    # Define video extensions to search for
    video_extensions = ['.mkv', '.mp4', '.avi', '.mov']
    all_videos = []
    
    # Find all video files
    for ext in video_extensions:
        videos = glob.glob(os.path.join(directory_path, f"*{ext}"))
        all_videos.extend(videos)
        
    if not all_videos:
        print(f"No video files found in {directory_path}")
        return
        
    print(f"Found {len(all_videos)} video files")
    
    # Create output directory if not specified
    if not output_dir:
        output_dir = os.path.join(directory_path, "analysis_reports")
        os.makedirs(output_dir, exist_ok=True)
        
    # Analyze each video
    for video_path in all_videos:
        print(f"\nAnalyzing {os.path.basename(video_path)}...")
        results = calculate_frame_times(video_path)
        if results:
            generate_report(results, output_dir)

def main():
    """Main function to handle command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Analyze video files to summarize frame rates and interframe intervals',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument('input', type=str,
                      help='Input video file or directory containing videos')
    parser.add_argument('--output-dir', type=str, default=None,
                      help='Directory to save analysis reports (defaults to "analysis_reports" subdir)')
    
    args = parser.parse_args()
    
    # Check if input is file or directory
    if os.path.isfile(args.input):
        # Analyze single file
        print(f"Analyzing single video file: {args.input}")
        results = calculate_frame_times(args.input)
        if results:
            # If output dir not specified, use the directory containing the input file
            output_dir = args.output_dir
            if not output_dir:
                output_dir = os.path.join(os.path.dirname(args.input), "analysis_reports")
            generate_report(results, output_dir)
    elif os.path.isdir(args.input):
        # Analyze all videos in directory
        print(f"Analyzing all videos in directory: {args.input}")
        analyze_directory(args.input, args.output_dir)
    else:
        print(f"Error: {args.input} is not a valid file or directory", file=sys.stderr)
        
if __name__ == "__main__":
    main() 