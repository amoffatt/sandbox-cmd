#!/usr/bin/env python3
"""Unit tests for named image functionality"""

import unittest
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import subprocess
import sys
import os

# Add parent directory to path to import box module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from box.cli import ConfigManager, ImageBuilder, ContainerRuntime


class TestNamedImages(unittest.TestCase):
    """Test cases for named image functionality"""
    
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
        
        # Mock container runtime
        self.runtime_patcher = patch('box.cli.shutil.which')
        self.mock_which = self.runtime_patcher.start()
        self.mock_which.return_value = '/usr/bin/docker'
    
    def tearDown(self):
        """Clean up test fixtures"""
        self.home_patcher.stop()
        self.runtime_patcher.stop()
        # Clean up temporary directory
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_get_box_image_name_with_custom_name(self):
        """Test generating box image name with custom name"""
        runtime = ContainerRuntime()
        image_builder = ImageBuilder(runtime)
        
        # Test with custom name
        name = image_builder.get_box_image_name('node:18', False, 'my-app')
        self.assertEqual(name, 'box-named-my-app')
        
        # Test with custom name and tmux
        name_tmux = image_builder.get_box_image_name('node:18', True, 'my-app')
        self.assertEqual(name_tmux, 'box-named-my-app-tmux')
        
        # Test without custom name (original behavior)
        name_default = image_builder.get_box_image_name('node:18', False, None)
        self.assertEqual(name_default, 'box-node-18')
    
    @patch('subprocess.run')
    def test_get_or_build_named_image(self, mock_run):
        """Test building or retrieving a named image from configuration"""
        runtime = ContainerRuntime()
        config_manager = ConfigManager()
        image_builder = ImageBuilder(runtime, config_manager)
        
        # Mock image doesn't exist
        mock_run.return_value = MagicMock(returncode=1, stdout='', stderr='')
        
        config = {
            'command': ['npm', 'start'],
            'node': True,
            'py': False,
            'image_version': '18',
            'tmux': False,
            'port': ['3000'],
            'read_only': [],
            'read_write': ['.']
        }
        
        # Mock successful pull and build
        with patch.object(image_builder, 'build_image', return_value=True):
            result = image_builder.get_or_build_named_image('test-app', config)
        
        self.assertEqual(result, 'box-named-test-app')
        
        # Verify pull was attempted
        calls = mock_run.call_args_list
        pull_call = [c for c in calls if 'pull' in str(c)]
        self.assertTrue(len(pull_call) > 0)
    
    @patch('subprocess.run')
    def test_get_or_build_named_image_exists(self, mock_run):
        """Test retrieving existing named image"""
        runtime = ContainerRuntime()
        config_manager = ConfigManager()
        image_builder = ImageBuilder(runtime, config_manager)
        
        # Mock image exists
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
        
        config = {
            'command': ['python', 'app.py'],
            'node': False,
            'py': True,
            'image_version': '3.9',
            'tmux': True,
            'port': ['8000'],
            'read_only': [],
            'read_write': ['/app']
        }
        
        result = image_builder.get_or_build_named_image('python-app', config)
        
        self.assertEqual(result, 'box-named-python-app-tmux')
        
        # Verify no build was attempted (image already exists)
        with patch.object(image_builder, 'build_image') as mock_build:
            result = image_builder.get_or_build_named_image('python-app', config)
            mock_build.assert_not_called()
    
    @patch('subprocess.run')
    def test_get_or_build_named_image_build_fails(self, mock_run):
        """Test handling of build failure for named image"""
        runtime = ContainerRuntime()
        config_manager = ConfigManager()
        image_builder = ImageBuilder(runtime, config_manager)
        
        # Mock image doesn't exist
        mock_run.return_value = MagicMock(returncode=1, stdout='', stderr='')
        
        config = {
            'command': ['node', 'server.js'],
            'node': True,
            'py': False,
            'image_version': None,
            'tmux': False,
            'port': [],
            'read_only': [],
            'read_write': []
        }
        
        # Mock build failure
        with patch.object(image_builder, 'build_image', return_value=False):
            result = image_builder.get_or_build_named_image('failing-app', config)
        
        self.assertIsNone(result)
    
    def test_args_reconstruction_from_config(self):
        """Test that Args class correctly reconstructs from config"""
        runtime = ContainerRuntime()
        config_manager = ConfigManager()
        image_builder = ImageBuilder(runtime, config_manager)
        
        config = {
            'command': ['npm', 'test'],
            'node': True,
            'py': False,
            'image_version': '16',
            'tmux': True,
            'port': ['3000', '8080:8080'],
            'read_only': ['/data'],
            'read_write': ['/code']
        }
        
        # Access the Args class used in get_or_build_named_image
        # We'll test the reconstruction logic indirectly
        with patch.object(image_builder, 'get_base_image') as mock_get_base:
            with patch.object(image_builder, 'image_exists', return_value=True):
                image_builder.get_or_build_named_image('test', config)
                
                # Check that get_base_image was called with properly reconstructed args
                args = mock_get_base.call_args[0][0]
                self.assertTrue(args.node)
                self.assertFalse(args.py)
                self.assertEqual(args.image_version, '16')
                self.assertTrue(args.tmux)
                self.assertEqual(args.command, ['npm', 'test'])
                self.assertEqual(args.name, 'test')
    
    def test_get_or_build_image_with_name(self):
        """Test get_or_build_image with name argument"""
        runtime = ContainerRuntime()
        config_manager = ConfigManager()
        image_builder = ImageBuilder(runtime, config_manager)
        
        # Create mock args with name
        args = MagicMock()
        args.name = 'custom-app'
        args.node = True
        args.py = False
        args.image_version = None
        args.tmux = False
        args.command = ['npm', 'start']
        
        with patch.object(image_builder, 'image_exists', return_value=True):
            result = image_builder.get_or_build_image(args)
            expected = 'box-named-custom-app'
            self.assertEqual(result, expected)
    
    def test_get_or_build_image_without_name(self):
        """Test get_or_build_image without name argument"""
        runtime = ContainerRuntime()
        config_manager = ConfigManager()
        image_builder = ImageBuilder(runtime, config_manager)
        
        # Create mock args without name attribute
        args = MagicMock()
        args.node = False
        args.py = True
        args.image_version = '3.10'
        args.tmux = True
        args.command = ['python']
        
        # Remove name attribute
        del args.name
        
        with patch.object(image_builder, 'image_exists', return_value=True):
            result = image_builder.get_or_build_image(args)
            expected = 'box-python-3.10-tmux'
            self.assertEqual(result, expected)


class TestIntegrationScenarios(unittest.TestCase):
    """Integration tests for named image scenarios"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_dir = tempfile.mkdtemp()
        self.config_dir = Path(self.test_dir) / '.box-cli'
        self.config_file = self.config_dir / 'config.json'
        
        # Patch home directory
        self.home_patcher = patch('box.cli.Path.home')
        self.mock_home = self.home_patcher.start()
        self.mock_home.return_value = Path(self.test_dir)
        
        # Mock container runtime detection
        self.runtime_patcher = patch('box.cli.shutil.which')
        self.mock_which = self.runtime_patcher.start()
        self.mock_which.return_value = '/usr/bin/docker'
    
    def tearDown(self):
        """Clean up test fixtures"""
        self.home_patcher.stop()
        self.runtime_patcher.stop()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_save_and_load_cycle(self):
        """Test complete save and load cycle for named image"""
        config_manager = ConfigManager()
        
        # Save configuration
        args_save = MagicMock()
        args_save.command = ['npm', 'run', 'dev']
        args_save.node = True
        args_save.py = False
        args_save.image_version = '18'
        args_save.tmux = True
        args_save.port = ['3000', '8080']
        args_save.read_only = ['/data']
        args_save.read_write = ['/app', '/config']
        
        config_manager.save_image_config('dev-env', args_save)
        
        # Load configuration
        loaded = config_manager.get_image_config('dev-env')
        
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded['command'], ['npm', 'run', 'dev'])
        self.assertTrue(loaded['node'])
        self.assertFalse(loaded['py'])
        self.assertEqual(loaded['image_version'], '18')
        self.assertTrue(loaded['tmux'])
        self.assertEqual(loaded['port'], ['3000', '8080'])
        self.assertEqual(loaded['read_only'], ['/data'])
        self.assertEqual(loaded['read_write'], ['/app', '/config'])
    
    def test_multiple_named_images(self):
        """Test managing multiple named images"""
        config_manager = ConfigManager()
        
        # Create multiple configurations
        configs = [
            ('web-app', {'node': True, 'command': ['npm', 'start'], 'port': ['3000']}),
            ('api-server', {'py': True, 'command': ['python', 'api.py'], 'port': ['8000']}),
            ('db-admin', {'py': False, 'command': ['mysql'], 'port': ['3306']}),
        ]
        
        for name, partial_config in configs:
            args = MagicMock()
            args.command = partial_config.get('command', [])
            args.node = partial_config.get('node', False)
            args.py = partial_config.get('py', False)
            args.image_version = None
            args.tmux = False
            args.port = partial_config.get('port', [])
            args.read_only = None
            args.read_write = None
            
            result = config_manager.save_image_config(name, args)
            self.assertTrue(result)
        
        # Verify all images are saved
        named_images = config_manager.list_named_images()
        self.assertEqual(len(named_images), 3)
        self.assertIn('web-app', named_images)
        self.assertIn('api-server', named_images)
        self.assertIn('db-admin', named_images)
        
        # Verify each config is correct
        web_config = config_manager.get_image_config('web-app')
        self.assertTrue(web_config['node'])
        self.assertEqual(web_config['command'], ['npm', 'start'])
        
        api_config = config_manager.get_image_config('api-server')
        self.assertTrue(api_config['py'])
        self.assertEqual(api_config['command'], ['python', 'api.py'])
    
    def test_config_persistence(self):
        """Test that configurations persist across ConfigManager instances"""
        # Create and save config with first instance
        config_manager1 = ConfigManager()
        
        args = MagicMock()
        args.command = ['node', 'index.js']
        args.node = True
        args.py = False
        args.image_version = '16'
        args.tmux = False
        args.port = ['4000']
        args.read_only = None
        args.read_write = ['.']
        
        config_manager1.save_image_config('persistent-app', args)
        
        # Create new instance and verify config is loaded
        config_manager2 = ConfigManager()
        
        loaded = config_manager2.get_image_config('persistent-app')
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded['command'], ['node', 'index.js'])
        self.assertTrue(loaded['node'])
        self.assertEqual(loaded['image_version'], '16')
        self.assertEqual(loaded['port'], ['4000'])
        self.assertEqual(loaded['read_write'], ['.'])
    
    def test_error_handling_for_missing_image(self):
        """Test error handling when named image doesn't exist"""
        config_manager = ConfigManager()
        
        # Try to get non-existent config
        result = config_manager.get_image_config('non-existent')
        self.assertIsNone(result)
        
        # List should be empty
        images = config_manager.list_named_images()
        self.assertEqual(images, [])


if __name__ == '__main__':
    unittest.main()