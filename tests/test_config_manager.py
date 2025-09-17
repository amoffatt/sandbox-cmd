#!/usr/bin/env python3
"""Unit tests for ConfigManager class"""

import unittest
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys
import os

# Add parent directory to path to import box module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from box.cli import ConfigManager


class BaseTestCase(unittest.TestCase):
    """Base test case with common setup and utilities"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Create a temporary directory for test configs
        self.test_dir = tempfile.mkdtemp()
        self.config_dir = Path(self.test_dir) / '.box-cli'
        self.config_file = self.config_dir / 'config.json'
        
        # Patch the home directory to use our test directory
        self.home_patcher = patch('box.cli.Path.home')
        self.mock_home = self.home_patcher.start()
        self.mock_home.return_value = Path(self.test_dir)
    
    def tearDown(self):
        """Clean up test fixtures"""
        self.home_patcher.stop()
        # Clean up temporary directory
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def create_mock_args(self, **kwargs):
        """Create a mock args object with common defaults"""
        defaults = {
            'command': [],
            'node': False,
            'py': False,
            'image_version': None,
            'tmux': False,
            'port': None,
            'read_only': None,
            'read_write': None
        }
        defaults.update(kwargs)
        
        args = MagicMock()
        for key, value in defaults.items():
            setattr(args, key, value)
        
        return args


class TestConfigManager(BaseTestCase):
    """Test cases for ConfigManager class"""
    
    def test_init_creates_config_dir(self):
        """Test that ConfigManager creates config directory if it doesn't exist"""
        self.assertFalse(self.config_dir.exists())
        
        config_manager = ConfigManager()
        
        self.assertTrue(self.config_dir.exists())
        self.assertTrue(self.config_dir.is_dir())
    
    def test_init_with_existing_config(self):
        """Test loading existing configuration"""
        # Create config directory and file
        self.config_dir.mkdir(parents=True)
        existing_config = {
            'images': {
                'test-image': {
                    'command': ['echo', 'test'],
                    'node': True,
                    'py': False
                }
            }
        }
        with open(self.config_file, 'w') as f:
            json.dump(existing_config, f)
        
        config_manager = ConfigManager()
        
        self.assertEqual(config_manager.config, existing_config)
    
    def test_init_with_corrupt_config(self):
        """Test handling of corrupt configuration file"""
        # Create config directory with corrupt JSON
        self.config_dir.mkdir(parents=True)
        with open(self.config_file, 'w') as f:
            f.write("{ corrupt json")
        
        config_manager = ConfigManager()
        
        # Should fall back to default config
        self.assertEqual(config_manager.config, {'images': {}})
    
    def test_save_image_config(self):
        """Test saving image configuration"""
        config_manager = ConfigManager()
        
        # Create mock args object
        args = self.create_mock_args(
            command=['npm', 'start'],
            node=True,
            image_version='18',
            tmux=True,
            port=['3000', '8080:8080'],
            read_only=['/data'],
            read_write=['/code']
        )
        
        result = config_manager.save_image_config('my-app', args)
        
        # Verify save was successful
        self.assertTrue(result)
        
        # Verify config was saved
        self.assertIn('my-app', config_manager.config['images'])
        saved_config = config_manager.config['images']['my-app']
        
        self.assertEqual(saved_config['command'], ['npm', 'start'])
        self.assertTrue(saved_config['node'])
        self.assertFalse(saved_config['py'])
        self.assertEqual(saved_config['image_version'], '18')
        self.assertTrue(saved_config['tmux'])
        self.assertEqual(saved_config['port'], ['3000', '8080:8080'])
        self.assertEqual(saved_config['read_only'], ['/data'])
        self.assertEqual(saved_config['read_write'], ['/code'])
        
        # Verify config was written to file
        with open(self.config_file, 'r') as f:
            file_config = json.load(f)
        self.assertEqual(file_config, config_manager.config)
    
    def test_save_image_config_with_none_values(self):
        """Test saving image configuration with None values for optional fields"""
        config_manager = ConfigManager()
        
        # Create mock args object with None values
        args = self.create_mock_args(
            command=[],
            py=True
        )
        
        config_manager.save_image_config('python-shell', args)
        
        saved_config = config_manager.config['images']['python-shell']
        self.assertEqual(saved_config['port'], [])
        self.assertEqual(saved_config['read_only'], [])
        self.assertEqual(saved_config['read_write'], [])
    
    def test_get_image_config(self):
        """Test retrieving image configuration"""
        config_manager = ConfigManager()
        
        # Add a test configuration
        test_config = {
            'command': ['node', 'app.js'],
            'node': True,
            'py': False,
            'image_version': '16',
            'tmux': False,
            'port': ['3000'],
            'read_only': [],
            'read_write': ['.']
        }
        config_manager.config['images']['test-app'] = test_config
        
        # Test getting existing config
        retrieved = config_manager.get_image_config('test-app')
        self.assertEqual(retrieved, test_config)
        
        # Test getting non-existent config
        non_existent = config_manager.get_image_config('non-existent')
        self.assertIsNone(non_existent)
    
    def test_list_named_images(self):
        """Test listing all named images"""
        config_manager = ConfigManager()
        
        # Start with empty config
        self.assertEqual(config_manager.list_named_images(), [])
        
        # Add some configurations
        config_manager.config['images']['app1'] = {'command': ['echo', '1']}
        config_manager.config['images']['app2'] = {'command': ['echo', '2']}
        config_manager.config['images']['app3'] = {'command': ['echo', '3']}
        
        named_images = config_manager.list_named_images()
        self.assertEqual(len(named_images), 3)
        self.assertIn('app1', named_images)
        self.assertIn('app2', named_images)
        self.assertIn('app3', named_images)
    
    def test_save_config_io_error(self):
        """Test handling of IO errors when saving config"""
        config_manager = ConfigManager()
        
        # Make config file read-only to trigger IO error
        if not self.config_dir.exists():
            self.config_dir.mkdir(parents=True)
        self.config_file.touch()
        os.chmod(self.config_file, 0o444)  # Read-only
        
        # Create mock args
        args = self.create_mock_args(command=['test'])
        
        # This should not raise an exception, just print a warning
        with patch('sys.stderr'):
            config_manager.save_image_config('test', args)
        
        # Config should still be updated in memory
        self.assertIn('test', config_manager.config['images'])
    
    def test_overwrite_existing_config_with_force(self):
        """Test that saving with same name and force=True overwrites existing config"""
        config_manager = ConfigManager()
        
        # Create initial config
        args1 = self.create_mock_args(
            command=['old', 'command'],
            node=True,
            image_version='14'
        )
        
        result1 = config_manager.save_image_config('my-app', args1)
        self.assertTrue(result1)
        
        # Overwrite with new config using force=True
        args2 = self.create_mock_args(
            command=['new', 'command'],
            py=True,
            image_version='3.9',
            tmux=True,
            port=['8000'],
            read_write=['/app']
        )
        
        result2 = config_manager.save_image_config('my-app', args2, force=True)
        self.assertTrue(result2)
        
        # Verify new config replaced old one
        saved = config_manager.config['images']['my-app']
        self.assertEqual(saved['command'], ['new', 'command'])
        self.assertFalse(saved['node'])
        self.assertTrue(saved['py'])
        self.assertEqual(saved['image_version'], '3.9')
        self.assertTrue(saved['tmux'])
        self.assertEqual(saved['port'], ['8000'])
        self.assertEqual(saved['read_write'], ['/app'])
    
    def test_overwrite_confirmation_prompt(self):
        """Test confirmation prompt when overwriting existing config"""
        config_manager = ConfigManager()
        
        # Create initial config
        args1 = self.create_mock_args(
            command=['npm', 'start'],
            node=True,
            port=['3000']
        )
        
        config_manager.save_image_config('test-app', args1)
        
        # Try to overwrite without force - simulate user saying 'no'
        args2 = self.create_mock_args(
            command=['npm', 'run', 'dev'],
            node=True,
            image_version='18',
            tmux=True,
            port=['3000', '8080'],
            read_write=['.']
        )
        
        with patch('builtins.input', return_value='n'):
            result = config_manager.save_image_config('test-app', args2)
            self.assertFalse(result)
        
        # Verify original config was not changed
        saved = config_manager.config['images']['test-app']
        self.assertEqual(saved['command'], ['npm', 'start'])
        self.assertIsNone(saved['image_version'])
        
        # Try again, simulate user saying 'yes'
        with patch('builtins.input', return_value='y'):
            result = config_manager.save_image_config('test-app', args2)
            self.assertTrue(result)
        
        # Verify config was updated
        saved = config_manager.config['images']['test-app']
        self.assertEqual(saved['command'], ['npm', 'run', 'dev'])
        self.assertEqual(saved['image_version'], '18')


if __name__ == '__main__':
    unittest.main()