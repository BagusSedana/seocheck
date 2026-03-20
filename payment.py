import os
import midtransclient
from dotenv import load_dotenv

load_dotenv()

class MidtransHelper:
    def __init__(self):
        self.server_key = os.getenv("MIDTRANS_SERVER_KEY", "").strip()
        self.client_key = os.getenv("MIDTRANS_CLIENT_KEY", "").strip()
        self.is_production = os.getenv("MIDTRANS_IS_PRODUCTION", "False").lower() == "true"
        
        self.snap = midtransclient.Snap(
            is_production=self.is_production,
            server_key=self.server_key,
            client_key=self.client_key
        )

    def create_transaction(self, order_id, amount, customer_details, item_details):
        """
        Create a Snap transaction and return the response containing token and redirect_url.
        """
        param = {
            "transaction_details": {
                "order_id": order_id,
                "gross_amount": amount
            },
            "customer_details": customer_details,
            "item_details": item_details,
            "usage_limit": 1
        }
        
        try:
            transaction = self.snap.create_transaction(param)
            return transaction
        except Exception as e:
            print(f"CRITICAL: Midtrans Error for {order_id}: {str(e)}")
            return None

    def get_status(self, order_id):
        """
        Get the latest status of a transaction from Midtrans.
        """
        try:
            status_response = self.snap.transactions.status(order_id)
            return status_response
        except Exception as e:
            print(f"Midtrans Status Error for {order_id}: {str(e)}")
            return None

    def verify_notification(self, notification_data):
        """
        Verify the notification from Midtrans.
        """
        try:
            status_response = self.snap.transactions.notification(notification_data)
            return status_response
        except Exception as e:
            print(f"Midtrans Verification Error: {str(e)}")
            return None

midtrans_helper = MidtransHelper()
