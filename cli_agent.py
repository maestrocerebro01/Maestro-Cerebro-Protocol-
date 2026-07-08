"""
CLI Agent System for Maestro Cerebro Protocol
Provides terminal-based agents for managing escrow transactions, payments, and protocol operations.
"""

import cmd
import sys
import os
import json
from typing import Optional, Dict, Any
from datetime import datetime
from tabulate import tabulate
import httpx
from dotenv import load_dotenv
import asyncio
from colorama import Fore, Back, Style, init

# Initialize colorama for colored terminal output
init(autoreset=True)

# Load environment variables
load_dotenv()

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8080")
GLOBAL_API_SECRET = os.getenv("GLOBAL_API_SECRET")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
DEVICE_ID = os.getenv("DEVICE_ID", "DEFAULT")
DEVICE_SECRET = os.getenv("DEVICE_SECRET")


class MaestroAgent(cmd.Cmd):
    """Interactive CLI agent for Maestro Cerebro Protocol management"""
    
    intro = f"""
    {Fore.CYAN}╔══════════════════════════════════════════════════════════════╗
    ║       Maestro Cerebro Protocol - CLI Agent Interface               ║
    ║                  v1.0 - Interactive Terminal Agent                 ║
    ╚══════════════════════════════════════════════════════════════╝{Style.RESET_ALL}
    
    Type {Fore.YELLOW}'help'{Style.RESET_ALL} to see available commands or {Fore.YELLOW}'exit'{Style.RESET_ALL} to quit.
    """
    
    prompt = f"{Fore.GREEN}maestro@cerebro> {Style.RESET_ALL}"
    
    def __init__(self):
        super().__init__()
        self.transactions: Dict[str, Dict[str, Any]] = {}
        self.authenticated = False
        self.client = httpx.AsyncClient(base_url=API_BASE_URL, timeout=30.0)
        self.headers = {
            "X-API-Key": GLOBAL_API_SECRET,
            "Device-ID": DEVICE_ID,
            "Device-Secret": DEVICE_SECRET,
        }
    
    def do_status(self, arg):
        """Check the service status - usage: status"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            response = loop.run_until_complete(self.client.get("/"))
            if response.status_code == 200:
                data = response.json()
                print(f"{Fore.GREEN}✓ Service Status: {data.get('status')}{Style.RESET_ALL}")
                print(f"  Message: {data.get('message')}")
            else:
                print(f"{Fore.RED}✗ Service Error: {response.status_code}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}✗ Connection Error: {str(e)}{Style.RESET_ALL}")
    
    def do_create_transaction(self, arg):
        """Create a new escrow transaction
        
        Usage: create_transaction <amount> <currency> <sender_id> <receiver_id>
        Example: create_transaction 100.00 USD user1 user2
        """
        args = arg.split()
        if len(args) < 4:
            print(f"{Fore.RED}Error: Missing arguments{Style.RESET_ALL}")
            print("Usage: create_transaction <amount> <currency> <sender_id> <receiver_id>")
            return
        
        try:
            amount = float(args[0])
            currency = args[1].upper()
            sender_id = args[2]
            receiver_id = args[3]
            
            transaction_data = {
                "amount": amount,
                "currency": currency,
                "sender_id": sender_id,
                "receiver_id": receiver_id,
            }
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            response = loop.run_until_complete(
                self.client.post("/transactions/", json=transaction_data, headers=self.headers)
            )
            
            if response.status_code == 200:
                tx = response.json()
                self.transactions[tx.get("id")] = tx
                print(f"{Fore.GREEN}✓ Transaction Created{Style.RESET_ALL}")
                self._print_transaction(tx)
            else:
                print(f"{Fore.RED}✗ Failed: {response.text}{Style.RESET_ALL}")
        except ValueError:
            print(f"{Fore.RED}Error: Invalid amount value{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}✗ Error: {str(e)}{Style.RESET_ALL}")
    
    def do_hold_funds(self, arg):
        """Hold funds for a transaction
        
        Usage: hold_funds <transaction_id>
        """
        if not arg.strip():
            print(f"{Fore.RED}Error: Missing transaction ID{Style.RESET_ALL}")
            return
        
        transaction_id = arg.strip()
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            response = loop.run_until_complete(
                self.client.post(f"/transactions/{transaction_id}/hold", headers=self.headers)
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"{Fore.GREEN}✓ Funds Held Successfully{Style.RESET_ALL}")
                self._print_transaction(data.get("transaction"))
            else:
                print(f"{Fore.RED}✗ Failed: {response.text}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}✗ Error: {str(e)}{Style.RESET_ALL}")
    
    def do_release_funds(self, arg):
        """Release held funds for a transaction
        
        Usage: release_funds <transaction_id>
        """
        if not arg.strip():
            print(f"{Fore.RED}Error: Missing transaction ID{Style.RESET_ALL}")
            return
        
        transaction_id = arg.strip()
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            response = loop.run_until_complete(
                self.client.post(f"/transactions/{transaction_id}/release", headers=self.headers)
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"{Fore.GREEN}✓ Funds Released Successfully{Style.RESET_ALL}")
                self._print_transaction(data.get("transaction"))
            else:
                print(f"{Fore.RED}✗ Failed: {response.text}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}✗ Error: {str(e)}{Style.RESET_ALL}")
    
    def do_cancel_transaction(self, arg):
        """Cancel a transaction
        
        Usage: cancel_transaction <transaction_id>
        """
        if not arg.strip():
            print(f"{Fore.RED}Error: Missing transaction ID{Style.RESET_ALL}")
            return
        
        transaction_id = arg.strip()
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            response = loop.run_until_complete(
                self.client.post(f"/transactions/{transaction_id}/cancel", headers=self.headers)
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"{Fore.GREEN}✓ Transaction Cancelled{Style.RESET_ALL}")
                self._print_transaction(data.get("transaction"))
            else:
                print(f"{Fore.RED}✗ Failed: {response.text}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}✗ Error: {str(e)}{Style.RESET_ALL}")
    
    def do_list_transactions(self, arg):
        """List all local transactions
        
        Usage: list_transactions
        """
        if not self.transactions:
            print(f"{Fore.YELLOW}No transactions yet{Style.RESET_ALL}")
            return
        
        table_data = []
        for tx_id, tx in self.transactions.items():
            table_data.append([
                tx_id[:8] + "...",
                tx.get("amount"),
                tx.get("currency"),
                tx.get("status").upper(),
                tx.get("sender_id"),
                tx.get("receiver_id"),
            ])
        
        headers = ["Transaction ID", "Amount", "Currency", "Status", "Sender", "Receiver"]
        print(f"\n{Fore.CYAN}{tabulate(table_data, headers=headers, tablefmt='grid')}{Style.RESET_ALL}\n")
    
    def do_view_transaction(self, arg):
        """View details of a specific transaction
        
        Usage: view_transaction <transaction_id>
        """
        if not arg.strip():
            print(f"{Fore.RED}Error: Missing transaction ID{Style.RESET_ALL}")
            return
        
        transaction_id = arg.strip()
        if transaction_id not in self.transactions:
            print(f"{Fore.RED}Transaction not found{Style.RESET_ALL}")
            return
        
        self._print_transaction(self.transactions[transaction_id])
    
    def do_create_payout(self, arg):
        """Create a PayPal payout
        
        Usage: create_payout <email> <amount> <currency>
        Example: create_payout user@example.com 50.00 USD
        """
        args = arg.split()
        if len(args) < 3:
            print(f"{Fore.RED}Error: Missing arguments{Style.RESET_ALL}")
            print("Usage: create_payout <email> <amount> <currency>")
            return
        
        try:
            email = args[0]
            amount = float(args[1])
            currency = args[2].upper()
            
            payout_data = {
                "recipient_email": email,
                "amount": amount,
                "currency": currency,
            }
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            admin_headers = {**self.headers, "Admin-Password": ADMIN_PASSWORD}
            response = loop.run_until_complete(
                self.client.post("/payouts", json=payout_data, headers=admin_headers)
            )
            
            if response.status_code == 200:
                print(f"{Fore.GREEN}✓ Payout Created{Style.RESET_ALL}")
                print(json.dumps(response.json(), indent=2))
            else:
                print(f"{Fore.RED}✗ Failed: {response.text}{Style.RESET_ALL}")
        except ValueError:
            print(f"{Fore.RED}Error: Invalid amount value{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}✗ Error: {str(e)}{Style.RESET_ALL}")
    
    def do_get_client_token(self, arg):
        """Get PayPal client token
        
        Usage: get_client_token
        """
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            response = loop.run_until_complete(
                self.client.get("/paypal-client-token", headers=self.headers)
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"{Fore.GREEN}✓ Client Token Retrieved{Style.RESET_ALL}")
                print(f"Token: {data.get('client_token')[:50]}...")
            else:
                print(f"{Fore.RED}✗ Failed: {response.text}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}✗ Error: {str(e)}{Style.RESET_ALL}")
    
    def do_export_transactions(self, arg):
        """Export transactions to a JSON file
        
        Usage: export_transactions [filename]
        Default: transactions_export.json
        """
        filename = arg.strip() or "transactions_export.json"
        try:
            with open(filename, 'w') as f:
                json.dump(self.transactions, f, indent=2, default=str)
            print(f"{Fore.GREEN}✓ Transactions exported to {filename}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}✗ Export failed: {str(e)}{Style.RESET_ALL}")
    
    def do_clear_local(self, arg):
        """Clear local transaction cache (doesn't delete from server)
        
        Usage: clear_local
        """
        self.transactions.clear()
        print(f"{Fore.YELLOW}Local transaction cache cleared{Style.RESET_ALL}")
    
    def do_help_admin(self, arg):
        """Show admin commands"""
        print(f"\n{Fore.CYAN}Admin Commands:{Style.RESET_ALL}")
        print("  create_payout       - Create a PayPal payout")
        print("  get_client_token    - Retrieve PayPal client token")
    
    def do_help_tx(self, arg):
        """Show transaction commands"""
        print(f"\n{Fore.CYAN}Transaction Commands:{Style.RESET_ALL}")
        print("  create_transaction  - Create a new escrow transaction")
        print("  hold_funds          - Hold funds for a transaction")
        print("  release_funds       - Release held funds")
        print("  cancel_transaction  - Cancel a transaction")
        print("  list_transactions   - List all transactions")
        print("  view_transaction    - View transaction details")
        print("  export_transactions - Export transactions to JSON")
    
    def do_help_util(self, arg):
        """Show utility commands"""
        print(f"\n{Fore.CYAN}Utility Commands:{Style.RESET_ALL}")
        print("  status              - Check service status")
        print("  clear_local         - Clear local transaction cache")
        print("  help_admin          - Show admin commands")
        print("  help_tx             - Show transaction commands")
        print("  help_util           - Show utility commands")
    
    def do_exit(self, arg):
        """Exit the CLI agent - usage: exit"""
        print(f"{Fore.YELLOW}Goodbye!{Style.RESET_ALL}")
        return True
    
    def do_quit(self, arg):
        """Quit the CLI agent - usage: quit"""
        return self.do_exit(arg)
    
    def _print_transaction(self, tx: Dict[str, Any]):
        """Pretty print a transaction"""
        print(f"\n{Fore.CYAN}Transaction Details:{Style.RESET_ALL}")
        print(f"  ID:              {tx.get('id')}")
        print(f"  PayPal Order ID: {tx.get('paypal_order_id', 'N/A')}")
        print(f"  Amount:          {tx.get('amount')} {tx.get('currency')}")
        print(f"  Status:          {Fore.YELLOW}{tx.get('status').upper()}{Style.RESET_ALL}")
        print(f"  Sender:          {tx.get('sender_id')}")
        print(f"  Receiver:        {tx.get('receiver_id')}")
        
        if tx.get('metadata'):
            print(f"  Metadata:")
            for key, value in tx['metadata'].items():
                if key == 'approval_url':
                    print(f"    {key}: {value[:60]}...")
                else:
                    print(f"    {key}: {value}")
        print()
    
    def default(self, line):
        """Handle unknown commands"""
        print(f"{Fore.RED}Unknown command: '{line}'. Type 'help' for available commands.{Style.RESET_ALL}")
    
    def emptyline(self):
        """Handle empty input"""
        pass


def main():
    """Entry point for the CLI agent"""
    agent = MaestroAgent()
    agent.cmdloop()


if __name__ == "__main__":
    main()
