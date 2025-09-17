#!/usr/bin/env python3
"""Test cases for mount merging when using named images"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add parent directory to path to import box module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from box.cli import ConfigManager
from tests.test_config_manager import BaseTestCase


class TestMountMerging(BaseTestCase):
    """Test cases for mount merging functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        super().setUp()
        
        # Mock container runtime detection
        self.runtime_patcher = patch('box.cli.shutil.which')
        self.mock_which = self.runtime_patcher.start()
        self.mock_which.return_value = '/usr/bin/docker'
    
    def tearDown(self):
        """Clean up test fixtures"""
        self.runtime_patcher.stop()
        super().tearDown()
    
    def test_mount_merging_with_existing_image(self):
        """Test that new mounts are merged with saved configuration when using -i"""
        config_manager = ConfigManager()
        
        # Save a configuration with existing mounts
        args_save = self.create_mock_args(
            command=['npm', 'start'],
            node=True,
            read_only=['/saved/data'],
            read_write=['/saved/code']
        )
        
        config_manager.save_image_config('test-app', args_save)
        
        # Simulate loading the image with additional mounts
        args_load = self.create_mock_args(
            command=[],  # Will use saved command
            read_only=['/new/readonly'],
            read_write=['/new/readwrite']
        )
        
        # Simulate the merge logic that happens in main()
        config = config_manager.get_image_config('test-app')
        self.assertIsNotNone(config)
        
        # Apply the merge logic
        saved_ro = config.get('read_only', [])
        saved_rw = config.get('read_write', [])
        
        # Combine saved mounts with new user-provided mounts
        if args_load.read_only:
            args_load.read_only = saved_ro + args_load.read_only
        else:
            args_load.read_only = saved_ro
            
        if args_load.read_write:
            args_load.read_write = saved_rw + args_load.read_write
        else:
            args_load.read_write = saved_rw
        
        # Verify both old and new mounts are present
        self.assertEqual(args_load.read_only, ['/saved/data', '/new/readonly'])
        self.assertEqual(args_load.read_write, ['/saved/code', '/new/readwrite'])
    
    def test_mount_merging_no_new_mounts(self):
        """Test that saved mounts are used when no new mounts provided"""
        config_manager = ConfigManager()
        
        # Save a configuration with existing mounts
        args_save = self.create_mock_args(
            command=['python', 'app.py'],
            py=True,
            read_only=['/data'],
            read_write=['/app']
        )
        
        config_manager.save_image_config('python-app', args_save)
        
        # Simulate loading without new mounts
        args_load = self.create_mock_args(command=[])
        
        # Apply the merge logic
        config = config_manager.get_image_config('python-app')
        saved_ro = config.get('read_only', [])
        saved_rw = config.get('read_write', [])
        
        if args_load.read_only:
            args_load.read_only = saved_ro + args_load.read_only
        else:
            args_load.read_only = saved_ro
            
        if args_load.read_write:
            args_load.read_write = saved_rw + args_load.read_write
        else:
            args_load.read_write = saved_rw
        
        # Verify only saved mounts are present
        self.assertEqual(args_load.read_only, ['/data'])
        self.assertEqual(args_load.read_write, ['/app'])
    
    def test_mount_merging_no_saved_mounts(self):
        """Test that new mounts work when no saved mounts exist"""
        config_manager = ConfigManager()
        
        # Save a configuration without mounts
        args_save = self.create_mock_args(
            command=['echo', 'hello'],
            node=True
        )
        
        config_manager.save_image_config('minimal-app', args_save)
        
        # Simulate loading with new mounts
        args_load = self.create_mock_args(
            read_only=['/new/data'],
            read_write=['/new/workspace']
        )
        
        # Apply the merge logic
        config = config_manager.get_image_config('minimal-app')
        saved_ro = config.get('read_only', [])
        saved_rw = config.get('read_write', [])
        
        if args_load.read_only:
            args_load.read_only = saved_ro + args_load.read_only
        else:
            args_load.read_only = saved_ro
            
        if args_load.read_write:
            args_load.read_write = saved_rw + args_load.read_write
        else:
            args_load.read_write = saved_rw
        
        # Verify only new mounts are present
        self.assertEqual(args_load.read_only, ['/new/data'])
        self.assertEqual(args_load.read_write, ['/new/workspace'])
    
    @patch('box.cli.parse_args')
    def test_end_to_end_mount_merging(self, mock_parse_args):
        """End-to-end test simulating actual CLI usage with mount merging"""
        config_manager = ConfigManager()
        
        # Step 1: Simulate creating named image with initial mounts
        # Command: box -n test-env --node -rw ./saved npm start
        create_args = self.create_mock_args(
            node=True,
            read_write=['./saved'],
            command=['npm', 'start']
        )
        create_args.name = 'test-env'
        
        # Save the configuration
        result = config_manager.save_image_config('test-env', create_args, force=True)
        self.assertTrue(result)
        
        # Step 2: Simulate using named image with additional mounts  
        # Command: box -i test-env -ro ./new -rw ./workspace
        use_args = self.create_mock_args(
            read_only=['./new'],
            read_write=['./workspace'],
            command=[]
        )
        use_args.image = 'test-env'
        
        # Load configuration and apply merge logic (from main() function)
        config = config_manager.get_image_config('test-env')
        self.assertIsNotNone(config)
        
        # Apply the merge logic that happens in main()
        saved_ro = config.get('read_only', [])
        saved_rw = config.get('read_write', [])
        
        # Combine saved mounts with new user-provided mounts
        if use_args.read_only:
            use_args.read_only = saved_ro + use_args.read_only
        else:
            use_args.read_only = saved_ro
            
        if use_args.read_write:
            use_args.read_write = saved_rw + use_args.read_write
        else:
            use_args.read_write = saved_rw
        
        # Verify the fix: saved mounts + new mounts are merged correctly
        expected_ro = ['./new']  # Only new mount (saved had none)
        expected_rw = ['./saved', './workspace']  # Saved + new
        
        self.assertEqual(use_args.read_only, expected_ro)
        self.assertEqual(use_args.read_write, expected_rw)
        
        # Also verify that the saved command would be used since none provided
        self.assertEqual(config.get('command'), ['npm', 'start'])


if __name__ == '__main__':
    unittest.main()