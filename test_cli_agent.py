"""
Test suite for the Maestro Cerebro CLI Agent
Tests the command-line interface functionality and API integration
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from io import StringIO
import json
import sys
from cli_agent import MaestroAgent


class TestMaestroAgent:
    """Test cases for the MaestroAgent CLI"""
    
    @pytest.fixture
    def agent(self):
        """Create a fresh agent instance for each test"""
        agent = MaestroAgent()
        agent.client = AsyncMock()
        return agent
    
    # Status Command Tests
    def test_status_success(self, agent, capsys):
        """Test successful service status check"""
        # Mock async response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": "Welcome to the Maestro Cerebro Escrow Service",
            "status": "active"
        }
        
        agent.client.get = AsyncMock(return_value=mock_response)
        
        # Capture output
        agent.do_status("")
        captured = capsys.readouterr()
        
        # Verify
        assert "active" in captured.out
        assert "✓" in captured.out
    
    def test_status_connection_error(self, agent, capsys):
        """Test status check with connection error"""
        agent.client.get = AsyncMock(side_effect=Exception("Connection refused"))
        
        agent.do_status("")
        captured = capsys.readouterr()
        
        assert "Connection Error" in captured.out
        assert "✗" in captured.out
    
    def test_status_http_error(self, agent, capsys):
        """Test status check with HTTP error"""
        mock_response = Mock()
        mock_response.status_code = 500
        agent.client.get = AsyncMock(return_value=mock_response)
        
        agent.do_status("")
        captured = capsys.readouterr()
        
        assert "Service Error" in captured.out
    
    # Create Transaction Tests
    def test_create_transaction_success(self, agent, capsys):
        """Test successful transaction creation"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "tx-123",
            "amount": 100.00,
            "currency": "USD",
            "status": "pending",
            "sender_id": "user1",
            "receiver_id": "user2",
            "paypal_order_id": None,
            "metadata": {}
        }
        
        agent.client.post = AsyncMock(return_value=mock_response)
        
        agent.do_create_transaction("100.00 USD user1 user2")
        captured = capsys.readouterr()
        
        assert "Transaction Created" in captured.out
        assert "✓" in captured.out
        assert "tx-123" in captured.out
        assert "tx-123" in agent.transactions
    
    def test_create_transaction_missing_args(self, agent, capsys):
        """Test transaction creation with missing arguments"""
        agent.do_create_transaction("100.00 USD user1")
        captured = capsys.readouterr()
        
        assert "Missing arguments" in captured.out
        assert "✗" in captured.out
    
    def test_create_transaction_invalid_amount(self, agent, capsys):
        """Test transaction creation with invalid amount"""
        agent.do_create_transaction("invalid_amount USD user1 user2")
        captured = capsys.readouterr()
        
        assert "Invalid amount" in captured.out
    
    def test_create_transaction_api_error(self, agent, capsys):
        """Test transaction creation with API error"""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"
        agent.client.post = AsyncMock(return_value=mock_response)
        
        agent.do_create_transaction("100.00 USD user1 user2")
        captured = capsys.readouterr()
        
        assert "Failed" in captured.out
    
    # Hold Funds Tests
    def test_hold_funds_success(self, agent, capsys):
        """Test successful fund holding"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": "Funds held successfully",
            "transaction": {
                "id": "tx-123",
                "amount": 100.00,
                "currency": "USD",
                "status": "held",
                "sender_id": "user1",
                "receiver_id": "user2",
                "paypal_order_id": None,
                "metadata": {}
            }
        }
        
        agent.client.post = AsyncMock(return_value=mock_response)
        
        agent.do_hold_funds("tx-123")
        captured = capsys.readouterr()
        
        assert "Funds Held Successfully" in captured.out
        assert "held" in captured.out
    
    def test_hold_funds_missing_id(self, agent, capsys):
        """Test hold funds with missing transaction ID"""
        agent.do_hold_funds("")
        captured = capsys.readouterr()
        
        assert "Missing transaction ID" in captured.out
    
    def test_hold_funds_api_error(self, agent, capsys):
        """Test hold funds with API error"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Transaction not found"
        agent.client.post = AsyncMock(return_value=mock_response)
        
        agent.do_hold_funds("invalid-tx")
        captured = capsys.readouterr()
        
        assert "Failed" in captured.out
    
    # Release Funds Tests
    def test_release_funds_success(self, agent, capsys):
        """Test successful fund release"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": "Funds released successfully",
            "transaction": {
                "id": "tx-123",
                "amount": 100.00,
                "currency": "USD",
                "status": "released",
                "sender_id": "user1",
                "receiver_id": "user2",
                "paypal_order_id": "paypal-123",
                "metadata": {"capture_id": "capture-123"}
            }
        }
        
        agent.client.post = AsyncMock(return_value=mock_response)
        
        agent.do_release_funds("tx-123")
        captured = capsys.readouterr()
        
        assert "Funds Released Successfully" in captured.out
        assert "released" in captured.out
    
    def test_release_funds_missing_id(self, agent, capsys):
        """Test release funds with missing transaction ID"""
        agent.do_release_funds("")
        captured = capsys.readouterr()
        
        assert "Missing transaction ID" in captured.out
    
    # Cancel Transaction Tests
    def test_cancel_transaction_success(self, agent, capsys):
        """Test successful transaction cancellation"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": "Transaction cancelled successfully",
            "transaction": {
                "id": "tx-123",
                "amount": 100.00,
                "currency": "USD",
                "status": "cancelled",
                "sender_id": "user1",
                "receiver_id": "user2",
                "paypal_order_id": None,
                "metadata": {}
            }
        }
        
        agent.client.post = AsyncMock(return_value=mock_response)
        
        agent.do_cancel_transaction("tx-123")
        captured = capsys.readouterr()
        
        assert "Transaction Cancelled" in captured.out
        assert "cancelled" in captured.out
    
    def test_cancel_transaction_missing_id(self, agent, capsys):
        """Test cancel transaction with missing ID"""
        agent.do_cancel_transaction("")
        captured = capsys.readouterr()
        
        assert "Missing transaction ID" in captured.out
    
    # List Transactions Tests
    def test_list_transactions_empty(self, agent, capsys):
        """Test listing with no transactions"""
        agent.do_list_transactions("")
        captured = capsys.readouterr()
        
        assert "No transactions yet" in captured.out
    
    def test_list_transactions_populated(self, agent, capsys):
        """Test listing with multiple transactions"""
        agent.transactions = {
            "tx-1": {
                "id": "tx-1",
                "amount": 100.00,
                "currency": "USD",
                "status": "pending",
                "sender_id": "user1",
                "receiver_id": "user2"
            },
            "tx-2": {
                "id": "tx-2",
                "amount": 50.00,
                "currency": "USD",
                "status": "released",
                "sender_id": "user3",
                "receiver_id": "user4"
            }
        }
        
        agent.do_list_transactions("")
        captured = capsys.readouterr()
        
        assert "tx-1" in captured.out
        assert "tx-2" in captured.out
        assert "pending" in captured.out
        assert "released" in captured.out
    
    # View Transaction Tests
    def test_view_transaction_success(self, agent, capsys):
        """Test viewing a transaction"""
        agent.transactions = {
            "tx-123": {
                "id": "tx-123",
                "amount": 100.00,
                "currency": "USD",
                "status": "held",
                "sender_id": "user1",
                "receiver_id": "user2",
                "paypal_order_id": "pp-123",
                "metadata": {"approval_url": "https://example.com/approve"}
            }
        }
        
        agent.do_view_transaction("tx-123")
        captured = capsys.readouterr()
        
        assert "Transaction Details" in captured.out
        assert "tx-123" in captured.out
        assert "100.00" in captured.out
        assert "held" in captured.out
    
    def test_view_transaction_not_found(self, agent, capsys):
        """Test viewing a non-existent transaction"""
        agent.do_view_transaction("invalid-tx")
        captured = capsys.readouterr()
        
        assert "Transaction not found" in captured.out
    
    def test_view_transaction_missing_id(self, agent, capsys):
        """Test view transaction with missing ID"""
        agent.do_view_transaction("")
        captured = capsys.readouterr()
        
        assert "Missing transaction ID" in captured.out
    
    # PayPal Tests
    def test_create_payout_success(self, agent, capsys):
        """Test successful payout creation"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "batch_header": {"payout_batch_id": "batch-123"},
            "success": True
        }
        
        agent.client.post = AsyncMock(return_value=mock_response)
        
        agent.do_create_payout("user@example.com 50.00 USD")
        captured = capsys.readouterr()
        
        assert "Payout Created" in captured.out
        assert "✓" in captured.out
    
    def test_create_payout_missing_args(self, agent, capsys):
        """Test payout creation with missing arguments"""
        agent.do_create_payout("user@example.com 50.00")
        captured = capsys.readouterr()
        
        assert "Missing arguments" in captured.out
    
    def test_create_payout_invalid_amount(self, agent, capsys):
        """Test payout creation with invalid amount"""
        agent.do_create_payout("user@example.com invalid USD")
        captured = capsys.readouterr()
        
        assert "Invalid amount" in captured.out
    
    def test_get_client_token_success(self, agent, capsys):
        """Test successful client token retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "client_token": "sample_token_1234567890abcdefghijklmnopqrstuvwxyz"
        }
        
        agent.client.get = AsyncMock(return_value=mock_response)
        
        agent.do_get_client_token("")
        captured = capsys.readouterr()
        
        assert "Client Token Retrieved" in captured.out
        assert "✓" in captured.out
    
    # Export Tests
    def test_export_transactions_success(self, agent, capsys, tmp_path):
        """Test successful transaction export"""
        export_file = tmp_path / "test_export.json"
        
        agent.transactions = {
            "tx-1": {
                "id": "tx-1",
                "amount": 100.00,
                "currency": "USD",
                "status": "pending",
                "sender_id": "user1",
                "receiver_id": "user2"
            }
        }
        
        agent.do_export_transactions(str(export_file))
        captured = capsys.readouterr()
        
        assert "exported" in captured.out
        assert export_file.exists()
        
        with open(export_file) as f:
            data = json.load(f)
            assert "tx-1" in data
    
    def test_export_transactions_error(self, agent, capsys):
        """Test export transactions with invalid path"""
        agent.do_export_transactions("/invalid/path/file.json")
        captured = capsys.readouterr()
        
        assert "Export failed" in captured.out
    
    # Clear Local Tests
    def test_clear_local(self, agent, capsys):
        """Test clearing local cache"""
        agent.transactions = {"tx-1": {}, "tx-2": {}}
        
        agent.do_clear_local("")
        captured = capsys.readouterr()
        
        assert "cache cleared" in captured.out
        assert len(agent.transactions) == 0
    
    # Help Tests
    def test_help_admin(self, agent, capsys):
        """Test admin help command"""
        agent.do_help_admin("")
        captured = capsys.readouterr()
        
        assert "Admin Commands" in captured.out
        assert "create_payout" in captured.out
    
    def test_help_tx(self, agent, capsys):
        """Test transaction help command"""
        agent.do_help_tx("")
        captured = capsys.readouterr()
        
        assert "Transaction Commands" in captured.out
        assert "create_transaction" in captured.out
    
    def test_help_util(self, agent, capsys):
        """Test utility help command"""
        agent.do_help_util("")
        captured = capsys.readouterr()
        
        assert "Utility Commands" in captured.out
        assert "status" in captured.out
    
    # Exit Tests
    def test_exit_command(self, agent, capsys):
        """Test exit command"""
        result = agent.do_exit("")
        captured = capsys.readouterr()
        
        assert result is True
        assert "Goodbye" in captured.out
    
    def test_quit_command(self, agent, capsys):
        """Test quit command"""
        result = agent.do_quit("")
        captured = capsys.readouterr()
        
        assert result is True
        assert "Goodbye" in captured.out
    
    # Unknown Command Tests
    def test_unknown_command(self, agent, capsys):
        """Test unknown command handling"""
        agent.onecmd("invalid_command")
        captured = capsys.readouterr()
        
        assert "Unknown command" in captured.out
        assert "✗" in captured.out
    
    # Empty Line Tests
    def test_empty_line(self, agent, capsys):
        """Test empty line handling"""
        agent.emptyline()
        captured = capsys.readouterr()
        
        assert captured.out == ""


# Integration Tests
class TestCLIIntegration:
    """Integration tests for the CLI agent"""
    
    @pytest.fixture
    def agent(self):
        agent = MaestroAgent()
        agent.client = AsyncMock()
        return agent
    
    def test_transaction_workflow(self, agent, capsys):
        """Test complete transaction workflow"""
        # 1. Create transaction
        create_response = Mock()
        create_response.status_code = 200
        create_response.json.return_value = {
            "id": "tx-workflow",
            "amount": 100.00,
            "currency": "USD",
            "status": "pending",
            "sender_id": "user1",
            "receiver_id": "user2",
            "paypal_order_id": None,
            "metadata": {}
        }
        
        agent.client.post = AsyncMock(return_value=create_response)
        agent.do_create_transaction("100.00 USD user1 user2")
        
        # 2. Hold funds
        hold_response = Mock()
        hold_response.status_code = 200
        hold_response.json.return_value = {
            "message": "Funds held successfully",
            "transaction": {
                "id": "tx-workflow",
                "status": "held",
                "amount": 100.00,
                "currency": "USD",
                "sender_id": "user1",
                "receiver_id": "user2",
                "paypal_order_id": None,
                "metadata": {}
            }
        }
        
        agent.client.post = AsyncMock(return_value=hold_response)
        agent.do_hold_funds("tx-workflow")
        
        # 3. Release funds
        release_response = Mock()
        release_response.status_code = 200
        release_response.json.return_value = {
            "message": "Funds released successfully",
            "transaction": {
                "id": "tx-workflow",
                "status": "released",
                "amount": 100.00,
                "currency": "USD",
                "sender_id": "user1",
                "receiver_id": "user2",
                "paypal_order_id": "pp-123",
                "metadata": {"capture_id": "cap-123"}
            }
        }
        
        agent.client.post = AsyncMock(return_value=release_response)
        agent.do_release_funds("tx-workflow")
        
        captured = capsys.readouterr()
        
        # Verify all steps completed successfully
        assert "Transaction Created" in captured.out
        assert "Funds Held Successfully" in captured.out
        assert "Funds Released Successfully" in captured.out


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
