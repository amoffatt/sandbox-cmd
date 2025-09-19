#!/usr/bin/env python3
"""Tests for network restriction features"""

import unittest
from unittest.mock import Mock, patch, call
import subprocess
from box.cli import NetworkManager, ContainerRuntime, parse_args


class TestNetworkManager(unittest.TestCase):
    """Test NetworkManager functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.runtime = Mock(spec=ContainerRuntime)
        self.runtime.runtime = 'docker'
        self.network_manager = NetworkManager(self.runtime)

    def test_no_network_configuration(self):
        """Test --no-network flag generates correct arguments"""
        args = Mock()
        args.no_network = True
        args.internal_network = False
        args.http_proxy = None

        network_args, env_vars = self.network_manager.get_network_args(args)

        self.assertEqual(network_args, ['--network', 'none'])
        self.assertEqual(env_vars, {})

    def test_internal_network_configuration(self):
        """Test --internal-network flag generates correct arguments"""
        args = Mock()
        args.no_network = False
        args.internal_network = True
        args.http_proxy = None

        with patch.object(self.network_manager, '_ensure_internal_network') as mock_ensure:
            network_args, env_vars = self.network_manager.get_network_args(args)

        self.assertEqual(network_args, ['--network', 'box-internal'])
        self.assertEqual(env_vars, {})
        mock_ensure.assert_called_once()

    def test_http_proxy_configuration(self):
        """Test --http-proxy flag generates correct environment variables"""
        args = Mock()
        args.no_network = False
        args.internal_network = False
        args.http_proxy = 'http://proxy.example.com:3128'

        network_args, env_vars = self.network_manager.get_network_args(args)

        self.assertEqual(network_args, [])
        expected_env = {
            'HTTP_PROXY': 'http://proxy.example.com:3128',
            'HTTPS_PROXY': 'http://proxy.example.com:3128',
            'http_proxy': 'http://proxy.example.com:3128',
            'https_proxy': 'http://proxy.example.com:3128'
        }
        self.assertEqual(env_vars, expected_env)

    def test_no_network_takes_precedence(self):
        """Test that --no-network takes precedence over --internal-network"""
        args = Mock()
        args.no_network = True
        args.internal_network = True  # This should be ignored
        args.http_proxy = None

        network_args, env_vars = self.network_manager.get_network_args(args)

        self.assertEqual(network_args, ['--network', 'none'])
        self.assertEqual(env_vars, {})

    def test_format_env_args(self):
        """Test environment variable formatting for container runtime"""
        env_vars = {
            'HTTP_PROXY': 'http://proxy:3128',
            'HTTPS_PROXY': 'http://proxy:3128'
        }

        env_args = self.network_manager.format_env_args(env_vars)

        expected = ['-e', 'HTTP_PROXY=http://proxy:3128', '-e', 'HTTPS_PROXY=http://proxy:3128']
        self.assertEqual(env_args, expected)

    @patch('subprocess.run')
    def test_ensure_internal_network_exists(self, mock_run):
        """Test internal network creation when network exists"""
        # Mock network inspect success (network exists)
        mock_run.return_value.returncode = 0

        self.network_manager._ensure_internal_network()

        # Should only check, not create
        mock_run.assert_called_once_with(
            ['docker', 'network', 'inspect', 'box-internal'],
            capture_output=True
        )

    @patch('subprocess.run')
    def test_ensure_internal_network_create(self, mock_run):
        """Test internal network creation when network doesn't exist"""
        # Mock network inspect failure (network doesn't exist), then creation success
        inspect_result = Mock()
        inspect_result.returncode = 1
        create_result = Mock()
        create_result.returncode = 0
        mock_run.side_effect = [inspect_result, create_result]

        self.network_manager._ensure_internal_network()

        # Should check then create
        expected_calls = [
            call(['docker', 'network', 'inspect', 'box-internal'], capture_output=True),
            call(['docker', 'network', 'create', '--internal', 'box-internal'], capture_output=True)
        ]
        mock_run.assert_has_calls(expected_calls)

    @patch('subprocess.run')
    @patch('builtins.print')
    def test_ensure_internal_network_create_failure(self, mock_print, mock_run):
        """Test handling of internal network creation failure"""
        # Mock network inspect failure, then creation failure
        inspect_result = Mock()
        inspect_result.returncode = 1
        create_result = Mock()
        create_result.returncode = 1
        create_result.stderr.decode.return_value = "Network creation failed"
        mock_run.side_effect = [inspect_result, create_result]

        self.network_manager._ensure_internal_network()

        # Should print warning about creation failure
        mock_print.assert_any_call("Warning: Failed to create internal network: Network creation failed")


class TestArgumentParsing(unittest.TestCase):
    """Test command line argument parsing for network options"""

    def test_no_network_flag_parsing(self):
        """Test parsing of --no-network flag"""
        with patch('sys.argv', ['box', '-N', 'python', 'script.py']):
            args = parse_args()

        self.assertTrue(hasattr(args, 'no_network'))
        self.assertTrue(args.no_network)
        self.assertEqual(args.command, ['python', 'script.py'])

    def test_internal_network_flag_parsing(self):
        """Test parsing of --internal-network flag"""
        with patch('sys.argv', ['box', '--internal-network', 'bash']):
            args = parse_args()

        self.assertTrue(hasattr(args, 'internal_network'))
        self.assertTrue(args.internal_network)
        self.assertEqual(args.command, ['bash'])

    def test_http_proxy_flag_parsing(self):
        """Test parsing of --http-proxy flag"""
        with patch('sys.argv', ['box', '--http-proxy', 'http://proxy:3128', 'curl', 'example.com']):
            args = parse_args()

        self.assertTrue(hasattr(args, 'http_proxy'))
        self.assertEqual(args.http_proxy, 'http://proxy:3128')
        self.assertEqual(args.command, ['curl', 'example.com'])

    def test_mutually_exclusive_network_flags(self):
        """Test that --no-network and --internal-network are mutually exclusive"""
        with patch('sys.argv', ['box', '-N', '--internal-network', 'bash']):
            with self.assertRaises(SystemExit):  # argparse should exit on conflicting args
                parse_args()

    def test_combined_flags(self):
        """Test combining proxy with other options"""
        with patch('sys.argv', ['box', '--http-proxy', 'http://proxy:3128', '-rw', '.', 'npm', 'install']):
            args = parse_args()

        self.assertEqual(args.http_proxy, 'http://proxy:3128')
        self.assertEqual(args.read_write, ['.'])
        self.assertEqual(args.command, ['npm', 'install'])


class TestNetworkIntegration(unittest.TestCase):
    """Test integration of network features with main functionality"""

    def test_network_args_added_to_container_command(self):
        """Test that network arguments are properly integrated into container run command"""
        # This would be tested in integration tests with actual container runtime
        # For now, we verify the NetworkManager produces the right arguments
        runtime = Mock(spec=ContainerRuntime)
        runtime.runtime = 'docker'
        network_manager = NetworkManager(runtime)

        # Test no-network
        args = Mock()
        args.no_network = True
        args.internal_network = False
        args.http_proxy = None

        network_args, env_vars = network_manager.get_network_args(args)
        env_args = network_manager.format_env_args(env_vars)

        # These should be added to the docker run command
        self.assertIn('--network', network_args)
        self.assertIn('none', network_args)
        self.assertEqual(len(env_args), 0)  # No environment variables for no-network

    def test_proxy_env_vars_formatting(self):
        """Test that proxy environment variables are correctly formatted"""
        runtime = Mock(spec=ContainerRuntime)
        runtime.runtime = 'podman'
        network_manager = NetworkManager(runtime)

        args = Mock()
        args.no_network = False
        args.internal_network = False
        args.http_proxy = 'http://corporate-proxy:8080'

        network_args, env_vars = network_manager.get_network_args(args)
        env_args = network_manager.format_env_args(env_vars)

        # Should have 4 environment variables (upper and lowercase variants)
        self.assertEqual(len(env_args), 8)  # 4 vars * 2 args each (-e VAR=value)
        self.assertIn('-e', env_args)
        self.assertIn('HTTP_PROXY=http://corporate-proxy:8080', env_args)


if __name__ == '__main__':
    unittest.main()