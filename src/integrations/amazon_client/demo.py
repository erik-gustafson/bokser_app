from copy import deepcopy


def demo_orders():
    order = {
        'orderId': '123-1234567-1234567',
        'createdTime': '2026-10-01T12:00:00Z', 'lastUpdatedTime': '2026-10-05T10:00:00Z',
        'salesChannel': {'channelName': 'AMAZON', 'marketplaceId': 'ATVPDKIKX0DER'},
        'fulfillment': {'fulfilledBy': 'MERCHANT', 'fulfillmentStatus': 'UNSHIPPED'},
        'recipient': {'deliveryAddress': {'name': 'Synthetic Test Recipient', 'addressLine1': '1 Test Street',
            'city': 'Minneapolis', 'stateOrRegion': 'MN', 'postalCode': '55401', 'countryCode': 'US'}},
        'orderItems': [{'orderItemId': 'TEST-ITEM-1', 'quantityOrdered': 2,
            'product': {'sellerSku': 'TEST-AMAZON-SKU', 'price': {'unitPrice': {'amount': '12.50', 'currencyCode': 'USD'}}}}],
    }
    fba = deepcopy(order)
    fba['orderId'] = '123-1234567-1234568'
    fba['fulfillment']['fulfilledBy'] = 'AMAZON'
    return [order, fba]
