from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import firebase_admin
from firebase_admin import credentials, firestore
import qrcode
import io
import base64
from datetime import datetime
import uuid
from datetime import datetime, timedelta
import csv
import os
import io

app = Flask(__name__)
app.secret_key = 'as-mobiles-secret-key-2025'  # Change this in production

# Initialize Firebase
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase_key.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

# Helper Functions
def get_next_set_number(item_code):
    """Get next set number for an item code"""
    sets = db.collection('inventory_sets').where('itemCode', '==', item_code).stream()
    existing_numbers = []
    
    for doc in sets:
        set_id = doc.to_dict()['setId']
        # Extract number from SET_631011004424_001 format
        try:
            number = int(set_id.split('_')[-1])
            existing_numbers.append(number)
        except:
            pass
    
    return max(existing_numbers, default=0) + 1

def validate_imei_numbers(imei_list):
    """Validate IMEI numbers format and uniqueness"""
    if len(imei_list) != 10:
        return False, f"Expected 10 IMEI numbers, got {len(imei_list)}"
    
    # Check format (15 digits each)
    for i, imei in enumerate(imei_list):
        if not imei.isdigit() or len(imei) != 15:
            return False, f"IMEI {i+1} invalid format: {imei} (should be 15 digits)"
    
    # Check for duplicates within the set
    if len(set(imei_list)) != 10:
        return False, "Duplicate IMEI numbers found in the set"
    
    # Check if any IMEI already exists in database
    for imei in imei_list:
        existing_sets = db.collection('inventory_sets').where('imeiNumbers', 'array_contains', imei).limit(1).stream()
        for existing_set in existing_sets:
            existing_data = existing_set.to_dict()
            return False, f"IMEI {imei} already exists in set {existing_data['setId']}"
    
    return True, "All IMEI numbers are valid"

@app.route('/')
def dashboard():
    """Dashboard page - now loads data via JavaScript"""
    return render_template('dashboard.html')
# ADD these missing routes to your app.py file

@app.route('/api/get_dashboard_stats', methods=['GET'])
def get_dashboard_stats():
    """Get dashboard statistics"""
    try:
        # Get all inventory sets
        all_sets = list(db.collection('inventory_sets').stream())
        
        # Calculate statistics
        total_products = len(set(s.to_dict().get('itemCode', '') for s in all_sets if s.to_dict().get('itemCode')))
        available_sets = len([s for s in all_sets if s.to_dict().get('status') == 'available'])
        total_phones = sum(s.to_dict().get('quantity', 0) for s in all_sets if s.to_dict().get('status') == 'available')
        pending_imei = len([s for s in all_sets if s.to_dict().get('status') == 'pending_imei'])
        
        stats = {
            'totalProducts': total_products,
            'availableSets': available_sets,
            'totalPhones': total_phones,
            'pendingIMEI': pending_imei
        }
        
        return jsonify({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        print(f"Error in get_dashboard_stats: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/get_recent_transactions', methods=['GET'])
def get_recent_transactions():
    """Get recent inward and outward transactions"""
    try:
        # Get recent inward transactions (last 5)
        recent_inward_query = db.collection('inward_transactions') \
                             .order_by('createdAt', direction=firestore.Query.DESCENDING) \
                             .limit(5)
        
        recent_inward = []
        for doc in recent_inward_query.stream():
            data = doc.to_dict()
            recent_inward.append({
                'invoiceNumber': data.get('invoiceNumber', ''),
                'supplier': data.get('supplier', ''),
                'totalQuantity': data.get('totalQuantity', 0),
                'totalSets': data.get('totalSets', 0),
                'createdAt': data.get('createdAt')
            })
        
        # Get recent outward transactions (last 5)
        recent_outward_query = db.collection('outward_transactions') \
                              .order_by('createdAt', direction=firestore.Query.DESCENDING) \
                              .limit(5)
        
        recent_outward = []
        for doc in recent_outward_query.stream():
            data = doc.to_dict()
            recent_outward.append({
                'invoiceNumber': data.get('invoiceNumber', ''),
                'customer': data.get('customer', ''),
                'totalQuantity': data.get('totalQuantity', 0),
                'createdAt': data.get('createdAt')
            })
        
        return jsonify({
            'success': True,
            'recentInward': recent_inward,
            'recentOutward': recent_outward
        })
        
    except Exception as e:
        print(f"Error in get_recent_transactions: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/get_low_stock_alerts', methods=['GET'])
def get_low_stock_alerts():
    """Get products with low stock levels"""
    try:
        # Get all available sets grouped by product
        sets = list(db.collection('inventory_sets')
                   .where(filter=firestore.FieldFilter('status', '==', 'available'))
                   .stream())
        
        # Group by item code
        products = {}
        for doc in sets:
            data = doc.to_dict()
            item_code = data.get('itemCode')
            
            if item_code not in products:
                products[item_code] = {
                    'itemCode': item_code,
                    'productName': data.get('productName'),
                    'brand': data.get('brand'),
                    'availableSets': 0,
                    'availableQuantity': 0
                }
            
            products[item_code]['availableSets'] += 1
            products[item_code]['availableQuantity'] += data.get('quantity', 0)
        
        # Define low stock threshold (configurable)
        low_stock_threshold = 5  # phones
        
        # Find low stock products
        low_stock_products = []
        for product in products.values():
            if product['availableQuantity'] <= low_stock_threshold:
                product['alertLevel'] = 'critical' if product['availableQuantity'] <= 2 else 'warning'
                low_stock_products.append(product)
        
        # Sort by quantity (lowest first)
        low_stock_products.sort(key=lambda x: x['availableQuantity'])
        
        return jsonify({
            'success': True,
            'lowStockProducts': low_stock_products,
            'threshold': low_stock_threshold
        })
        
    except Exception as e:
        print(f"Error in get_low_stock_alerts: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    

@app.route('/inward')
def inward_page():
    """Smart inward stock entry page - supports auto-complete and smart features"""
    return render_template('inward.html')

@app.route('/outward')
def outward_page():
    """Outward sales page with cart functionality"""
    return render_template('outward.html')

# Replace your existing inventory route in app.py with this enhanced version

@app.route('/inventory')
def inventory_page():
    """Enhanced inventory page with summary data"""
    try:
        # Get basic summary for initial page load
        all_sets = list(db.collection('inventory_sets').stream())
        
        # Calculate summary
        summary = {
            'available_sets': len([doc for doc in all_sets if doc.to_dict().get('status') == 'available']),
            'pending_sets': len([doc for doc in all_sets if doc.to_dict().get('status') == 'pending_imei']),
            'sold_sets': len([doc for doc in all_sets if doc.to_dict().get('status') == 'sold']),
            'unique_products': len(set(doc.to_dict().get('itemCode') for doc in all_sets if doc.to_dict().get('itemCode'))),
            'available_phones': sum(doc.to_dict().get('quantity', 0) for doc in all_sets if doc.to_dict().get('status') == 'available'),
            'total_sets': len(all_sets)
        }
        
        return render_template('inventory.html', summary=summary, sets=[])
        
    except Exception as e:
        print(f"Inventory page error: {str(e)}")
        flash(f'Error loading inventory: {str(e)}', 'error')
        return render_template('inventory.html', summary={
            'available_sets': 0,
            'pending_sets': 0,
            'sold_sets': 0,
            'unique_products': 0,
            'available_phones': 0,
            'total_sets': 0
        }, sets=[])


# Add these routes to your app.py file for enhanced inventory functionality

import csv
import io
from flask import make_response

@app.route('/api/get_inventory_data', methods=['GET'])
def get_inventory_data():
    """Get all inventory data with enhanced details for the inventory page"""
    try:
        # Get all inventory sets
        sets = db.collection('inventory_sets').order_by('createdAt', direction=firestore.Query.DESCENDING).stream()
        sets_list = []
        
        for doc in sets:
            set_data = doc.to_dict()
            # Ensure all required fields exist with safe defaults
            safe_set = {
                'id': doc.id,
                'setId': set_data.get('setId', 'Unknown'),
                'itemCode': set_data.get('itemCode', 'Unknown'),
                'productName': set_data.get('productName', 'Unknown Product'),
                'brand': set_data.get('brand', 'Unknown'),
                'quantity': set_data.get('quantity', 0),
                'status': set_data.get('status', 'unknown'),
                'hsnCode': set_data.get('hsnCode', ''),
                'imeiNumbers': set_data.get('imeiNumbers', []),
                'purchaseDetails': set_data.get('purchaseDetails', {}),
                'saleDetails': set_data.get('saleDetails', {}),
                'createdAt': set_data.get('createdAt'),
                'updatedAt': set_data.get('updatedAt')
            }
            sets_list.append(safe_set)
        
        return jsonify({
            'success': True,
            'inventory': sets_list
        })
        
    except Exception as e:
        print(f"Error in get_inventory_data: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/get_set_details', methods=['POST'])
def get_set_details():
    """Get detailed information for a specific set"""
    try:
        data = request.json
        set_id = data.get('setId')
        
        if not set_id:
            return jsonify({'error': 'Set ID is required'}), 400
        
        # Get set data
        set_doc = db.collection('inventory_sets').document(set_id).get()
        
        if not set_doc.exists:
            return jsonify({'error': 'Set not found'}), 404
        
        set_data = set_doc.to_dict()
        
        # Format the data properly
        formatted_set = {
            'id': set_doc.id,
            'setId': set_data.get('setId'),
            'itemCode': set_data.get('itemCode'),
            'productName': set_data.get('productName'),
            'brand': set_data.get('brand'),
            'quantity': set_data.get('quantity'),
            'status': set_data.get('status'),
            'hsnCode': set_data.get('hsnCode'),
            'imeiNumbers': set_data.get('imeiNumbers', []),
            'purchaseDetails': set_data.get('purchaseDetails', {}),
            'saleDetails': set_data.get('saleDetails'),
            'createdAt': set_data.get('createdAt'),
            'updatedAt': set_data.get('updatedAt')
        }
        
        return jsonify({
            'success': True,
            'set': formatted_set
        })
        
    except Exception as e:
        print(f"Error in get_set_details: {str(e)}")
        return jsonify({'error': str(e)}), 500


# Add these two new endpoints to your app.py file

@app.route('/api/search_invoice', methods=['POST'])
def search_invoice():
    """Search for transactions and inventory by invoice number"""
    try:
        data = request.json
        invoice_number = data.get('invoiceNumber', '').strip()
        
        if not invoice_number:
            return jsonify({'success': False, 'error': 'Invoice number is required'})
        
        result_data = {}
        
        # Search in inward transactions
        inward_query = db.collection('inward_transactions') \
                        .where(filter=firestore.FieldFilter('invoiceNumber', '==', invoice_number)) \
                        .limit(1)
        
        inward_docs = list(inward_query.stream())
        if inward_docs:
            result_data['inward'] = inward_docs[0].to_dict()
        
        # Search in outward transactions  
        outward_query = db.collection('outward_transactions') \
                         .where(filter=firestore.FieldFilter('invoiceNumber', '==', invoice_number)) \
                         .limit(1)
        
        outward_docs = list(outward_query.stream())
        if outward_docs:
            result_data['outward'] = outward_docs[0].to_dict()
        
        # Search in inventory sets (purchase invoice)
        sets_query = db.collection('inventory_sets') \
                      .where(filter=firestore.FieldFilter('purchaseDetails.invoiceNumber', '==', invoice_number))
        
        sets_docs = list(sets_query.stream())
        if sets_docs:
            result_data['sets'] = [doc.to_dict() for doc in sets_docs]
        
        # Search in inventory sets (sale invoice)
        if not sets_docs:
            sale_sets_query = db.collection('inventory_sets') \
                            .where(filter=firestore.FieldFilter('saleDetails.invoiceNumber', '==', invoice_number))
            
            sale_sets_docs = list(sale_sets_query.stream())
            if sale_sets_docs:
                result_data['sets'] = [doc.to_dict() for doc in sale_sets_docs]
        
        if not result_data:
            return jsonify({'success': False, 'error': 'Invoice not found'})
        
        return jsonify({
            'success': True,
            'data': result_data
        })
        
    except Exception as e:
        print(f"Error in search_invoice: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/export_invoice_tracking', methods=['POST'])
def export_invoice_tracking():
    """Export comprehensive invoice tracking report as CSV"""
    try:
        # Get all transactions and inventory sets
        inward_transactions = list(db.collection('inward_transactions').stream())
        outward_transactions = list(db.collection('outward_transactions').stream())
        inventory_sets = list(db.collection('inventory_sets').stream())
        
        # Create CSV content
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Invoice Tracking Report - Generated on ' + datetime.now().strftime('%Y-%m-%d %H:%M')])
        writer.writerow([''])
        
        # INWARD TRANSACTIONS SECTION
        writer.writerow(['INWARD TRANSACTIONS'])
        writer.writerow(['Invoice Number', 'Supplier', 'Invoice Date', 'Total Quantity', 'Total Sets', 'Created Date', 'Products Added'])
        
        for trans in inward_transactions:
            data = trans.to_dict()
            created_date = ''
            if data.get('createdAt'):
                try:
                    created_date = data['createdAt'].strftime('%Y-%m-%d %H:%M')
                except:
                    created_date = str(data['createdAt'])
            
            # Get products added in this transaction
            related_sets = [s.to_dict() for s in inventory_sets 
                          if s.to_dict().get('purchaseDetails', {}).get('invoiceNumber') == data.get('invoiceNumber')]
            
            products_list = []
            for set_data in related_sets:
                products_list.append(f"{set_data.get('setId', '')} ({set_data.get('productName', '')})")
            
            writer.writerow([
                data.get('invoiceNumber', ''),
                data.get('supplier', ''),
                data.get('invoiceDate', ''),
                data.get('totalQuantity', 0),
                data.get('totalSets', 0),
                created_date,
                '; '.join(products_list[:3]) + ('...' if len(products_list) > 3 else '')
            ])
        
        writer.writerow([''])
        
        # OUTWARD TRANSACTIONS SECTION
        writer.writerow(['OUTWARD TRANSACTIONS'])
        writer.writerow(['Invoice Number', 'Customer', 'Total Quantity', 'Created Date', 'Products Sold'])
        
        for trans in outward_transactions:
            data = trans.to_dict()
            created_date = ''
            if data.get('createdAt'):
                try:
                    created_date = data['createdAt'].strftime('%Y-%m-%d %H:%M')
                except:
                    created_date = str(data['createdAt'])
            
            # Get products sold in this transaction
            related_sets = [s.to_dict() for s in inventory_sets 
                          if s.to_dict().get('saleDetails', {}).get('invoiceNumber') == data.get('invoiceNumber')]
            
            products_list = []
            for set_data in related_sets:
                products_list.append(f"{set_data.get('setId', '')} ({set_data.get('productName', '')})")
            
            writer.writerow([
                data.get('invoiceNumber', ''),
                data.get('customer', ''),
                data.get('totalQuantity', 0),
                created_date,
                '; '.join(products_list[:3]) + ('...' if len(products_list) > 3 else '')
            ])
        
        writer.writerow([''])
        
        # DETAILED INVENTORY TRACKING SECTION
        writer.writerow(['DETAILED INVENTORY TRACKING'])
        writer.writerow(['Set ID', 'Product Name', 'Brand', 'Status', 'Quantity', 'Purchase Invoice', 'Purchase Supplier', 'Purchase Date', 'Sale Invoice', 'Sale Customer', 'Sale Date', 'IMEI Count'])
        
        for set_doc in inventory_sets:
            data = set_doc.to_dict()
            
            purchase_invoice = data.get('purchaseDetails', {}).get('invoiceNumber', '')
            purchase_supplier = data.get('purchaseDetails', {}).get('supplier', '')
            purchase_date = data.get('purchaseDetails', {}).get('date', '')
            
            sale_invoice = data.get('saleDetails', {}).get('invoiceNumber', '')
            sale_customer = data.get('saleDetails', {}).get('customer', '')
            sale_date = data.get('saleDetails', {}).get('date', '')
            
            imei_count = len(data.get('imeiNumbers', []))
            
            created_date = ''
            if data.get('createdAt'):
                try:
                    created_date = data['createdAt'].strftime('%Y-%m-%d')
                except:
                    created_date = str(data['createdAt'])
            
            writer.writerow([
                data.get('setId', ''),
                data.get('productName', ''),
                data.get('brand', ''),
                data.get('status', ''),
                data.get('quantity', 0),
                purchase_invoice,
                purchase_supplier,
                purchase_date or created_date,
                sale_invoice,
                sale_customer,
                sale_date,
                imei_count
            ])
        
        writer.writerow([''])
        
        # INVOICE SUMMARY SECTION
        writer.writerow(['INVOICE SUMMARY'])
        writer.writerow(['Invoice Number', 'Type', 'Date', 'Supplier/Customer', 'Total Quantity', 'Status'])
        
        # Combine all invoices
        all_invoices = {}
        
        # Add inward invoices
        for trans in inward_transactions:
            data = trans.to_dict()
            invoice_num = data.get('invoiceNumber', '')
            if invoice_num:
                all_invoices[invoice_num] = {
                    'type': 'Inward',
                    'date': data.get('invoiceDate', ''),
                    'party': data.get('supplier', ''),
                    'quantity': data.get('totalQuantity', 0),
                    'status': 'Completed'
                }
        
        # Add outward invoices
        for trans in outward_transactions:
            data = trans.to_dict()
            invoice_num = data.get('invoiceNumber', '')
            if invoice_num:
                all_invoices[invoice_num] = {
                    'type': 'Outward',
                    'date': data.get('createdAt', ''),
                    'party': data.get('customer', ''),
                    'quantity': data.get('totalQuantity', 0),
                    'status': 'Completed'
                }
        
        # Write invoice summary
        for invoice_num, details in sorted(all_invoices.items()):
            writer.writerow([
                invoice_num,
                details['type'],
                details['date'],
                details['party'],
                details['quantity'],
                details['status']
            ])
        
        # Create response
        csv_content = output.getvalue()
        output.close()
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=invoice_tracking_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'
        
        return response
        
    except Exception as e:
        print(f"Error in export_invoice_tracking: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
    
@app.route('/api/export_inventory_csv', methods=['POST'])
def export_inventory_csv():
    """Export inventory data to CSV with filtering options"""
    try:
        data = request.json
        export_type = data.get('exportType', 'all')  # 'all' or 'filtered'
        filters = data.get('filters', {})
        
        # Get all inventory sets
        sets_query = db.collection('inventory_sets').order_by('createdAt', direction=firestore.Query.DESCENDING)
        all_sets = list(sets_query.stream())
        
        # Apply filters if export_type is 'filtered'
        filtered_sets = []
        
        for set_doc in all_sets:
            set_data = set_doc.to_dict()
            
            # Apply filters if specified
            if export_type == 'filtered':
                # Status filter
                if filters.get('status') and set_data.get('status') != filters['status']:
                    continue
                
                # Brand filter
                if filters.get('brand') and set_data.get('brand') != filters['brand']:
                    continue
                
                # Item code filter
                if filters.get('itemCode'):
                    if filters['itemCode'].lower() not in set_data.get('itemCode', '').lower():
                        continue
                
                # Product name filter
                if filters.get('productName'):
                    if filters['productName'].lower() not in set_data.get('productName', '').lower():
                        continue
                
                # Supplier filter
                if filters.get('supplier'):
                    purchase_details = set_data.get('purchaseDetails', {})
                    if purchase_details.get('supplier') != filters['supplier']:
                        continue
                
                # Date filters
                if filters.get('dateFrom') or filters.get('dateTo'):
                    created_at = set_data.get('createdAt')
                    if created_at:
                        try:
                            if hasattr(created_at, 'date'):
                                set_date = created_at.date()
                            else:
                                set_date = datetime.fromisoformat(str(created_at)).date()
                            
                            if filters.get('dateFrom'):
                                from_date = datetime.strptime(filters['dateFrom'], '%Y-%m-%d').date()
                                if set_date < from_date:
                                    continue
                            
                            if filters.get('dateTo'):
                                to_date = datetime.strptime(filters['dateTo'], '%Y-%m-%d').date()
                                if set_date > to_date:
                                    continue
                        except:
                            # Skip if date parsing fails
                            continue
            
            # Format set data for CSV
            purchase_details = set_data.get('purchaseDetails', {})
            sale_details = set_data.get('saleDetails', {})
            
            csv_row = {
                'Set ID': set_data.get('setId', ''),
                'Item Code': set_data.get('itemCode', ''),
                'Product Name': set_data.get('productName', ''),
                'Brand': set_data.get('brand', ''),
                'HSN Code': set_data.get('hsnCode', ''),
                'Quantity': set_data.get('quantity', 0),
                'Status': set_data.get('status', ''),
                'IMEI Count': len(set_data.get('imeiNumbers', [])),
                'IMEI Numbers': '; '.join(set_data.get('imeiNumbers', [])),
                'Purchase Invoice': purchase_details.get('invoiceNumber', ''),
                'Purchase Date': purchase_details.get('invoiceDate', ''),
                'Supplier': purchase_details.get('supplier', ''),
                'Sale Invoice': sale_details.get('invoiceNumber', '') if sale_details else '',
                'Customer': sale_details.get('customer', '') if sale_details else '',
                'Sale Date': sale_details.get('date', '') if sale_details else '',
                'Created At': str(set_data.get('createdAt', '')),
                'Updated At': str(set_data.get('updatedAt', ''))
            }
            
            filtered_sets.append(csv_row)
        
        # Create CSV content
        output = io.StringIO()
        if filtered_sets:
            fieldnames = filtered_sets[0].keys()
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(filtered_sets)
        else:
            # Empty CSV with headers
            fieldnames = [
                'Set ID', 'Item Code', 'Product Name', 'Brand', 'HSN Code', 'Quantity', 
                'Status', 'IMEI Count', 'IMEI Numbers', 'Purchase Invoice', 'Purchase Date', 
                'Supplier', 'Sale Invoice', 'Customer', 'Sale Date', 'Created At', 'Updated At'
            ]
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
        
        # Create response
        csv_content = output.getvalue()
        output.close()
        
        # Generate filename
        today = datetime.now().strftime('%Y-%m-%d')
        filename = f"inventory_{export_type}_{today}.csv"
        
        # Create response with CSV content
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        
        return response
        
    except Exception as e:
        print(f"Error in export_inventory_csv: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/get_inventory_summary', methods=['GET'])
def get_inventory_summary_enhanced():
    """Get enhanced inventory summary with detailed statistics"""
    try:
        # Get all sets
        all_sets = list(db.collection('inventory_sets').stream())
        
        # Initialize counters
        summary = {
            'total_sets': len(all_sets),
            'available_sets': 0,
            'sold_sets': 0,
            'pending_sets': 0,
            'available_phones': 0,
            'sold_phones': 0,
            'pending_phones': 0,
            'unique_products': set(),
            'brands': set(),
            'suppliers': set()
        }
        
        # Process each set
        for doc in all_sets:
            data = doc.to_dict()
            status = data.get('status', 'unknown')
            quantity = data.get('quantity', 0)
            
            # Count by status
            if status == 'available':
                summary['available_sets'] += 1
                summary['available_phones'] += quantity
            elif status == 'sold':
                summary['sold_sets'] += 1
                summary['sold_phones'] += quantity
            elif status == 'pending_imei':
                summary['pending_sets'] += 1
                summary['pending_phones'] += quantity
            
            # Track unique values
            if data.get('itemCode'):
                summary['unique_products'].add(data['itemCode'])
            if data.get('brand'):
                summary['brands'].add(data['brand'])
            
            purchase_details = data.get('purchaseDetails', {})
            if purchase_details.get('supplier'):
                summary['suppliers'].add(purchase_details['supplier'])
        
        # Convert sets to counts
        summary['unique_products'] = len(summary['unique_products'])
        summary['total_brands'] = len(summary['brands'])
        summary['total_suppliers'] = len(summary['suppliers'])
        summary['total_phones'] = summary['available_phones'] + summary['sold_phones'] + summary['pending_phones']
        
        # Remove the sets (we only want counts)
        del summary['brands']
        del summary['suppliers']
        
        return jsonify({
            'success': True,
            'summary': summary
        })
        
    except Exception as e:
        print(f"Error in get_inventory_summary_enhanced: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/search_inventory', methods=['POST'])
def search_inventory():
    """Search inventory with advanced filters"""
    try:
        data = request.json
        search_term = data.get('searchTerm', '').strip().lower()
        filters = data.get('filters', {})
        
        # Get all inventory sets
        sets_query = db.collection('inventory_sets')
        all_sets = list(sets_query.stream())
        
        results = []
        
        for doc in all_sets:
            set_data = doc.to_dict()
            
            # Apply search term
            if search_term:
                searchable_text = ' '.join([
                    set_data.get('setId', ''),
                    set_data.get('itemCode', ''),
                    set_data.get('productName', ''),
                    set_data.get('brand', ''),
                    set_data.get('purchaseDetails', {}).get('supplier', '')
                ]).lower()
                
                if search_term not in searchable_text:
                    continue
            
            # Apply filters
            if filters.get('status') and set_data.get('status') != filters['status']:
                continue
            
            if filters.get('brand') and set_data.get('brand') != filters['brand']:
                continue
            
            # Format result
            result = {
                'id': doc.id,
                'setId': set_data.get('setId'),
                'itemCode': set_data.get('itemCode'),
                'productName': set_data.get('productName'),
                'brand': set_data.get('brand'),
                'quantity': set_data.get('quantity'),
                'status': set_data.get('status'),
                'supplier': set_data.get('purchaseDetails', {}).get('supplier', ''),
                'createdAt': set_data.get('createdAt')
            }
            
            results.append(result)
        
        # Sort results by relevance (exact matches first)
        if search_term:
            results.sort(key=lambda x: (
                search_term not in x['itemCode'].lower(),
                search_term not in x['setId'].lower(),
                x['productName']
            ))
        
        return jsonify({
            'success': True,
            'results': results[:50]  # Limit to 50 results
        })
        
    except Exception as e:
        print(f"Error in search_inventory: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/bulk_update_status', methods=['POST'])
def bulk_update_status():
    """Bulk update status for multiple sets"""
    try:
        data = request.json
        set_ids = data.get('setIds', [])
        new_status = data.get('newStatus', '')
        
        if not set_ids or not new_status:
            return jsonify({'error': 'Set IDs and new status are required'}), 400
        
        valid_statuses = ['available', 'sold', 'pending_imei']
        if new_status not in valid_statuses:
            return jsonify({'error': f'Invalid status. Must be one of: {valid_statuses}'}), 400
        
        updated_count = 0
        errors = []
        
        for set_id in set_ids:
            try:
                # Update the set
                db.collection('inventory_sets').document(set_id).update({
                    'status': new_status,
                    'updatedAt': datetime.now()
                })
                updated_count += 1
                
            except Exception as e:
                errors.append(f'Error updating set {set_id}: {str(e)}')
        
        return jsonify({
            'success': True,
            'message': f'Successfully updated {updated_count} sets',
            'updated_count': updated_count,
            'errors': errors
        })
        
    except Exception as e:
        print(f"Error in bulk_update_status: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/get_inventory_analytics', methods=['GET'])
def get_inventory_analytics():
    """Get inventory analytics and insights"""
    try:
        # Get all sets
        all_sets = list(db.collection('inventory_sets').stream())
        
        # Initialize analytics
        analytics = {
            'totalValue': 0,  # We'll skip cost calculations as per requirement
            'topBrands': {},
            'statusDistribution': {
                'available': 0,
                'sold': 0,
                'pending_imei': 0
            },
            'monthlyTrends': {},
            'supplierAnalysis': {},
            'recentActivity': []
        }
        
        # Process each set
        for doc in all_sets:
            data = doc.to_dict()
            
            # Status distribution
            status = data.get('status', 'unknown')
            if status in analytics['statusDistribution']:
                analytics['statusDistribution'][status] += 1
            
            # Brand analysis
            brand = data.get('brand', 'Unknown')
            if brand not in analytics['topBrands']:
                analytics['topBrands'][brand] = {
                    'total': 0,
                    'available': 0,
                    'sold': 0
                }
            analytics['topBrands'][brand]['total'] += 1
            if status == 'available':
                analytics['topBrands'][brand]['available'] += 1
            elif status == 'sold':
                analytics['topBrands'][brand]['sold'] += 1
            
            # Supplier analysis
            purchase_details = data.get('purchaseDetails', {})
            supplier = purchase_details.get('supplier', 'Unknown')
            if supplier not in analytics['supplierAnalysis']:
                analytics['supplierAnalysis'][supplier] = {
                    'totalSets': 0,
                    'totalPhones': 0
                }
            analytics['supplierAnalysis'][supplier]['totalSets'] += 1
            analytics['supplierAnalysis'][supplier]['totalPhones'] += data.get('quantity', 0)
            
            # Monthly trends
            created_at = data.get('createdAt')
            if created_at:
                try:
                    if hasattr(created_at, 'strftime'):
                        month_key = created_at.strftime('%Y-%m')
                    else:
                        month_key = str(created_at)[:7]  # Take first 7 chars (YYYY-MM)
                    
                    if month_key not in analytics['monthlyTrends']:
                        analytics['monthlyTrends'][month_key] = {
                            'inward': 0,
                            'phones': 0
                        }
                    analytics['monthlyTrends'][month_key]['inward'] += 1
                    analytics['monthlyTrends'][month_key]['phones'] += data.get('quantity', 0)
                except:
                    pass
        
        # Sort top brands by total count
        analytics['topBrands'] = dict(sorted(
            analytics['topBrands'].items(),
            key=lambda x: x[1]['total'],
            reverse=True
        )[:10])
        
        # Sort suppliers by total phones
        analytics['supplierAnalysis'] = dict(sorted(
            analytics['supplierAnalysis'].items(),
            key=lambda x: x[1]['totalPhones'],
            reverse=True
        )[:10])
        
        return jsonify({
            'success': True,
            'analytics': analytics
        })
        
    except Exception as e:
        print(f"Error in get_inventory_analytics: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/update_set_info', methods=['POST'])
def update_set_info():
    """Update basic information for a set"""
    try:
        data = request.json
        set_id = data.get('setId')
        updates = data.get('updates', {})
        
        if not set_id:
            return jsonify({'error': 'Set ID is required'}), 400
        
        # Validate set exists
        set_doc = db.collection('inventory_sets').document(set_id).get()
        if not set_doc.exists:
            return jsonify({'error': 'Set not found'}), 404
        
        # Allowed fields to update
        allowed_fields = [
            'productName', 'brand', 'hsnCode', 'quantity'
        ]
        
        valid_updates = {}
        for field, value in updates.items():
            if field in allowed_fields:
                valid_updates[field] = value
        
        if not valid_updates:
            return jsonify({'error': 'No valid fields to update'}), 400
        
        # Add update timestamp
        valid_updates['updatedAt'] = datetime.now()
        
        # Update the set
        db.collection('inventory_sets').document(set_id).update(valid_updates)
        
        return jsonify({
            'success': True,
            'message': f'Set {set_id} updated successfully',
            'updated_fields': list(valid_updates.keys())
        })
        
    except Exception as e:
        print(f"Error in update_set_info: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate_inventory_report', methods=['POST'])
def generate_inventory_report():
    """Generate comprehensive inventory report"""
    try:
        data = request.json
        report_type = data.get('reportType', 'summary')  # 'summary', 'detailed', 'analytics'
        date_range = data.get('dateRange', {})
        
        # Get inventory data
        sets_query = db.collection('inventory_sets')
        
        # Apply date filter if specified
        if date_range.get('from'):
            from_date = datetime.strptime(date_range['from'], '%Y-%m-%d')
            sets_query = sets_query.where('createdAt', '>=', from_date)
        
        if date_range.get('to'):
            to_date = datetime.strptime(date_range['to'], '%Y-%m-%d')
            sets_query = sets_query.where('createdAt', '<=', to_date)
        
        all_sets = list(sets_query.stream())
        
        # Generate report based on type
        if report_type == 'summary':
            report = generate_summary_report(all_sets)
        elif report_type == 'detailed':
            report = generate_detailed_report(all_sets)
        elif report_type == 'analytics':
            report = generate_analytics_report(all_sets)
        else:
            return jsonify({'error': 'Invalid report type'}), 400
        
        return jsonify({
            'success': True,
            'report': report,
            'generated_at': datetime.now().isoformat(),
            'total_sets': len(all_sets)
        })
        
    except Exception as e:
        print(f"Error in generate_inventory_report: {str(e)}")
        return jsonify({'error': str(e)}), 500

def generate_summary_report(sets):
    """Generate summary report"""
    summary = {
        'total_sets': len(sets),
        'by_status': {},
        'by_brand': {},
        'total_phones': 0
    }
    
    for doc in sets:
        data = doc.to_dict()
        status = data.get('status', 'unknown')
        brand = data.get('brand', 'Unknown')
        quantity = data.get('quantity', 0)
        
        # Count by status
        summary['by_status'][status] = summary['by_status'].get(status, 0) + 1
        
        # Count by brand
        summary['by_brand'][brand] = summary['by_brand'].get(brand, 0) + quantity
        
        # Total phones
        summary['total_phones'] += quantity
    
    return summary

def generate_detailed_report(sets):
    """Generate detailed report"""
    detailed = {
        'sets': [],
        'summary': generate_summary_report(sets)
    }
    
    for doc in sets:
        data = doc.to_dict()
        set_info = {
            'setId': data.get('setId'),
            'itemCode': data.get('itemCode'),
            'productName': data.get('productName'),
            'brand': data.get('brand'),
            'quantity': data.get('quantity'),
            'status': data.get('status'),
            'createdAt': str(data.get('createdAt')),
            'supplier': data.get('purchaseDetails', {}).get('supplier', ''),
            'invoiceNumber': data.get('purchaseDetails', {}).get('invoiceNumber', '')
        }
        detailed['sets'].append(set_info)
    
    return detailed

def generate_analytics_report(sets):
    """Generate analytics report"""
    return {
        'summary': generate_summary_report(sets),
        'trends': analyze_trends(sets),
        'performance': analyze_performance(sets)
    }

def analyze_trends(sets):
    """Analyze inventory trends"""
    monthly_data = {}
    
    for doc in sets:
        data = doc.to_dict()
        created_at = data.get('createdAt')
        
        if created_at:
            try:
                if hasattr(created_at, 'strftime'):
                    month = created_at.strftime('%Y-%m')
                else:
                    month = str(created_at)[:7]
                
                if month not in monthly_data:
                    monthly_data[month] = {'sets': 0, 'phones': 0}
                
                monthly_data[month]['sets'] += 1
                monthly_data[month]['phones'] += data.get('quantity', 0)
            except:
                pass
    
    return monthly_data

def analyze_performance(sets):
    """Analyze inventory performance"""
    performance = {
        'top_products': {},
        'supplier_performance': {}
    }
    
    for doc in sets:
        data = doc.to_dict()
        item_code = data.get('itemCode', 'Unknown')
        supplier = data.get('purchaseDetails', {}).get('supplier', 'Unknown')
        
        # Track product performance
        if item_code not in performance['top_products']:
            performance['top_products'][item_code] = {
                'total_quantity': 0,
                'total_sets': 0,
                'productName': data.get('productName', '')
            }
        
        performance['top_products'][item_code]['total_quantity'] += data.get('quantity', 0)
        performance['top_products'][item_code]['total_sets'] += 1
        
        # Track supplier performance
        if supplier not in performance['supplier_performance']:
            performance['supplier_performance'][supplier] = {
                'total_sets': 0,
                'total_phones': 0
            }
        
        performance['supplier_performance'][supplier]['total_sets'] += 1
        performance['supplier_performance'][supplier]['total_phones'] += data.get('quantity', 0)
    
    # Sort by performance
    performance['top_products'] = dict(sorted(
        performance['top_products'].items(),
        key=lambda x: x[1]['total_quantity'],
        reverse=True
    )[:10])
    
    performance['supplier_performance'] = dict(sorted(
        performance['supplier_performance'].items(),
        key=lambda x: x[1]['total_phones'],
        reverse=True
    )[:10])
    
    return performance

@app.route('/reports')
def reports_page():
    """Enhanced reports page (no financial calculations)"""
    try:
        # Get summary data
        all_sets = list(db.collection('inventory_sets').stream())
        available_sets = [doc for doc in all_sets if doc.to_dict()['status'] == 'available']
        sold_sets = [doc for doc in all_sets if doc.to_dict()['status'] == 'sold']
        
        # Get transactions
        inward_transactions = list(db.collection('inward_transactions').stream())
        outward_transactions = list(db.collection('outward_transactions').stream())
        
        summary = {
            'total_sets': len(all_sets),
            'available_sets': len(available_sets),
            'sold_sets': len(sold_sets),
            'total_phones_available': sum(doc.to_dict()['quantity'] for doc in available_sets),
            'total_phones_sold': sum(doc.to_dict()['quantity'] for doc in sold_sets),
            'total_inward_transactions': len(inward_transactions),
            'total_outward_transactions': len(outward_transactions),
            'inward_transactions': [doc.to_dict() for doc in inward_transactions],
            'outward_transactions': [doc.to_dict() for doc in outward_transactions]
        }
        
        return render_template('reports.html', summary=summary)
    
    except Exception as e:
        print(f"Reports error: {str(e)}")  # Debug log
        flash(f'Error loading reports: {str(e)}', 'error')
        return render_template('reports.html', summary={
            'total_sets': 0,
            'available_sets': 0,
            'sold_sets': 0,
            'total_phones_available': 0,
            'total_phones_sold': 0,
            'total_inward_transactions': 0,
            'total_outward_transactions': 0,
            'inward_transactions': [],
            'outward_transactions': []
        })

# API Routes for Smart Inward System
@app.route('/api/get_existing_products', methods=['GET'])
def get_existing_products():
    """Get all existing products for auto-complete"""
    try:
        # Get all inventory sets and group by item code
        all_sets = list(db.collection('inventory_sets').stream())
        products = {}
        
        for set_doc in all_sets:
            set_data = set_doc.to_dict()
            item_code = set_data.get('itemCode', '')
            
            if item_code not in products:
                products[item_code] = {
                    'itemCode': item_code,
                    'productName': set_data.get('productName', ''),
                    'brand': set_data.get('brand', ''),
                    'hsnCode': set_data.get('hsnCode', ''),
                    'supplier': set_data.get('purchaseDetails', {}).get('supplier', ''),
                    'totalQuantity': 0,
                    'totalSets': 0,
                    'lastUpdated': set_data.get('updatedAt', set_data.get('createdAt'))
                }
            
            # Add to totals
            products[item_code]['totalQuantity'] += set_data.get('quantity', 0)
            products[item_code]['totalSets'] += 1
            
            # Update last updated date if newer
            current_date = set_data.get('updatedAt', set_data.get('createdAt'))
            if current_date and current_date > products[item_code]['lastUpdated']:
                products[item_code]['lastUpdated'] = current_date
        
        # Convert to list and filter out empty item codes
        products_list = [p for p in products.values() if p['itemCode']]
        
        return jsonify({
            'success': True,
            'products': products_list
        })
        
    except Exception as e:
        print(f"Error in get_existing_products: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/check_invoice_exists', methods=['POST'])
def check_invoice_exists():
    """Check if invoice number already exists"""
    try:
        data = request.json
        invoice_number = data.get('invoiceNumber', '').strip()
        
        if not invoice_number:
            return jsonify({'exists': False})
        
        # Check in inward transactions
        existing_inward = list(db.collection('inward_transactions')
                             .where('invoiceNumber', '==', invoice_number)
                             .limit(1)
                             .stream())
        
        if existing_inward:
            return jsonify({
                'exists': True,
                'type': 'inward',
                'details': existing_inward[0].to_dict()
            })
        
        # Check in outward transactions
        existing_outward = list(db.collection('outward_transactions')
                              .where('invoiceNumber', '==', invoice_number)
                              .limit(1)
                              .stream())
        
        if existing_outward:
            return jsonify({
                'exists': True,
                'type': 'outward',
                'details': existing_outward[0].to_dict()
            })
        
        return jsonify({'exists': False})
        
    except Exception as e:
        print(f"Error in check_invoice_exists: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/add_to_existing_product', methods=['POST'])
def add_to_existing_product():
    """Add quantity to existing product"""
    try:
        data = request.json
        
        # Validate required fields
        required_fields = [
            'purchaseInvoice', 'invoiceDate', 'itemCode', 'brand', 
            'productName', 'hsnCode', 'supplierName', 'totalQuantity', 
            'numberOfSets', 'imeiNumbers'
        ]
        
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Validate quantities
        total_quantity = int(data['totalQuantity'])
        number_of_sets = int(data['numberOfSets'])
        
        # Validate IMEI numbers
        imei_numbers = data['imeiNumbers']
        is_valid, validation_message = validate_imei_numbers(imei_numbers)
        if not is_valid:
            return jsonify({'error': f'IMEI validation failed: {validation_message}'}), 400
        
        # Check if invoice number already exists
        existing_invoice = list(db.collection('inward_transactions')
                              .where('invoiceNumber', '==', data['purchaseInvoice'])
                              .limit(1)
                              .stream())
        
        if existing_invoice:
            return jsonify({'error': f'Invoice number {data["purchaseInvoice"]} already exists'}), 400
        
        # Create new sets for existing product
        sets_created = []
        
        # Calculate how many complete sets (10 phones each) we can make
        complete_sets = total_quantity // 10
        remaining_phones = total_quantity % 10
        
        # Create complete sets
        for i in range(complete_sets):
            set_number = get_next_set_number(data['itemCode'])
            set_id = f"SET_{data['itemCode']}_{set_number:03d}"
            
            # For the first set, use the scanned IMEI numbers
            if i == 0:
                set_imeis = imei_numbers
                set_quantity = 10
                set_status = 'available'
            else:
                # Additional sets need IMEI numbers to be added later
                set_imeis = []
                set_quantity = 10
                set_status = 'pending_imei'
            
            set_data = {
                'setId': set_id,
                'itemCode': data['itemCode'],
                'productName': data['productName'],
                'brand': data['brand'],
                'hsnCode': data['hsnCode'],
                'quantity': set_quantity,
                'status': set_status,
                'imeiNumbers': set_imeis,
                'purchaseDetails': {
                    'invoiceNumber': data['purchaseInvoice'],
                    'invoiceDate': data['invoiceDate'],
                    'supplier': data['supplierName'],
                    'date': datetime.now().strftime('%Y-%m-%d')
                },
                'saleDetails': None,
                'createdAt': datetime.now(),
                'updatedAt': datetime.now()
            }
            
            db.collection('inventory_sets').document(set_id).set(set_data)
            sets_created.append(set_id)
        
        # Create partial set if there are remaining phones
        if remaining_phones > 0:
            set_number = get_next_set_number(data['itemCode'])
            set_id = f"SET_{data['itemCode']}_{set_number:03d}"
            
            partial_set_data = {
                'setId': set_id,
                'itemCode': data['itemCode'],
                'productName': data['productName'],
                'brand': data['brand'],
                'hsnCode': data['hsnCode'],
                'quantity': remaining_phones,
                'status': 'pending_imei',  # Partial sets need IMEI numbers
                'imeiNumbers': [],
                'purchaseDetails': {
                    'invoiceNumber': data['purchaseInvoice'],
                    'invoiceDate': data['invoiceDate'],
                    'supplier': data['supplierName'],
                    'date': datetime.now().strftime('%Y-%m-%d')
                },
                'saleDetails': None,
                'createdAt': datetime.now(),
                'updatedAt': datetime.now()
            }
            
            db.collection('inventory_sets').document(set_id).set(partial_set_data)
            sets_created.append(set_id)
        
        # Create inward transaction record
        transaction_data = {
            'invoiceNumber': data['purchaseInvoice'],
            'invoiceDate': data['invoiceDate'],
            'supplier': data['supplierName'],
            'items': [{
                'itemCode': data['itemCode'],
                'productName': data['productName'],
                'brand': data['brand'],
                'hsnCode': data['hsnCode'],
                'totalQuantity': total_quantity,
                'quantityPerSet': 10,
                'setsCreated': len(sets_created),
                'addedToExisting': True
            }],
            'totalQuantity': total_quantity,
            'totalSets': len(sets_created),
            'sets': sets_created,
            'imeiCount': len(imei_numbers),
            'createdBy': 'admin',
            'createdAt': datetime.now(),
            'entryType': 'added_to_existing_product'
        }
        
        db.collection('inward_transactions').add(transaction_data)
        
        return jsonify({
            'success': True,
            'message': f'Successfully added {total_quantity} phones to existing product {data["productName"]}',
            'sets_created': sets_created,
            'total_quantity': total_quantity,
            'total_sets': len(sets_created),
            'imei_count': len(imei_numbers),
            'complete_sets': complete_sets,
            'partial_set_phones': remaining_phones if remaining_phones > 0 else None
        })
    
    except Exception as e:
        print(f"Error in add_to_existing_product: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/add_inward', methods=['POST'])
def add_inward():
    """Add new inward stock entry - Enhanced version with smart features"""
    try:
        data = request.json
        
        # Validate required fields
        required_fields = [
            'purchaseInvoice', 'invoiceDate', 'itemCode', 'brand', 
            'productName', 'hsnCode', 'supplierName', 'totalQuantity', 
            'numberOfSets', 'imeiNumbers'
        ]
        
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Validate quantities
        total_quantity = int(data['totalQuantity'])
        number_of_sets = int(data['numberOfSets'])
        
        # Validate IMEI numbers
        imei_numbers = data['imeiNumbers']
        is_valid, validation_message = validate_imei_numbers(imei_numbers)
        if not is_valid:
            return jsonify({'error': f'IMEI validation failed: {validation_message}'}), 400
        
        # Check if invoice number already exists
        existing_invoice = list(db.collection('inward_transactions')
                              .where('invoiceNumber', '==', data['purchaseInvoice'])
                              .limit(1)
                              .stream())
        
        if existing_invoice:
            return jsonify({'error': f'Invoice number {data["purchaseInvoice"]} already exists'}), 400
        
        # Create sets
        sets_created = []
        
        # Calculate how many complete sets (10 phones each) we can make
        complete_sets = total_quantity // 10
        remaining_phones = total_quantity % 10
        
        # Create complete sets
        for i in range(complete_sets):
            set_number = get_next_set_number(data['itemCode'])
            set_id = f"SET_{data['itemCode']}_{set_number:03d}"
            
            # For the first set, use the scanned IMEI numbers
            if i == 0:
                set_imeis = imei_numbers
                set_quantity = 10
                set_status = 'available'
            else:
                # Additional sets need IMEI numbers to be added later
                set_imeis = []
                set_quantity = 10
                set_status = 'pending_imei'
            
            set_data = {
                'setId': set_id,
                'itemCode': data['itemCode'],
                'productName': data['productName'],
                'brand': data['brand'],
                'hsnCode': data['hsnCode'],
                'quantity': set_quantity,
                'status': set_status,
                'imeiNumbers': set_imeis,
                'purchaseDetails': {
                    'invoiceNumber': data['purchaseInvoice'],
                    'invoiceDate': data['invoiceDate'],
                    'supplier': data['supplierName'],
                    'date': datetime.now().strftime('%Y-%m-%d')
                },
                'saleDetails': None,
                'createdAt': datetime.now(),
                'updatedAt': datetime.now()
            }
            
            db.collection('inventory_sets').document(set_id).set(set_data)
            sets_created.append(set_id)
        
        # Create partial set if there are remaining phones
        if remaining_phones > 0:
            set_number = get_next_set_number(data['itemCode'])
            set_id = f"SET_{data['itemCode']}_{set_number:03d}"
            
            partial_set_data = {
                'setId': set_id,
                'itemCode': data['itemCode'],
                'productName': data['productName'],
                'brand': data['brand'],
                'hsnCode': data['hsnCode'],
                'quantity': remaining_phones,
                'status': 'pending_imei',  # Partial sets need IMEI numbers
                'imeiNumbers': [],
                'purchaseDetails': {
                    'invoiceNumber': data['purchaseInvoice'],
                    'invoiceDate': data['invoiceDate'],
                    'supplier': data['supplierName'],
                    'date': datetime.now().strftime('%Y-%m-%d')
                },
                'saleDetails': None,
                'createdAt': datetime.now(),
                'updatedAt': datetime.now()
            }
            
            db.collection('inventory_sets').document(set_id).set(partial_set_data)
            sets_created.append(set_id)
        
        # Create inward transaction record
        transaction_data = {
            'invoiceNumber': data['purchaseInvoice'],
            'invoiceDate': data['invoiceDate'],
            'supplier': data['supplierName'],
            'items': [{
                'itemCode': data['itemCode'],
                'productName': data['productName'],
                'brand': data['brand'],
                'hsnCode': data['hsnCode'],
                'totalQuantity': total_quantity,
                'quantityPerSet': 10,
                'setsCreated': len(sets_created)
            }],
            'totalQuantity': total_quantity,
            'totalSets': len(sets_created),
            'sets': sets_created,
            'imeiCount': len(imei_numbers),
            'createdBy': 'admin',
            'createdAt': datetime.now(),
            'entryType': 'new_product_with_smart_sets'
        }
        
        db.collection('inward_transactions').add(transaction_data)
        
        return jsonify({
            'success': True,
            'message': f'Successfully created new product with {len(sets_created)} sets and {total_quantity} phones',
            'sets_created': sets_created,
            'total_quantity': total_quantity,
            'total_sets': len(sets_created),
            'imei_count': len(imei_numbers),
            'complete_sets': complete_sets,
            'partial_set_phones': remaining_phones if remaining_phones > 0 else None
        })
    
    except Exception as e:
        print(f"Error in add_inward: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/get_product_stats', methods=['POST'])
def get_product_stats():
    """Get statistics for a specific product by item code"""
    try:
        data = request.json
        item_code = data.get('itemCode', '').strip()
        
        if not item_code:
            return jsonify({'error': 'Item code is required'}), 400
        
        # Get all sets for this item code
        sets = list(db.collection('inventory_sets')
                   .where('itemCode', '==', item_code)
                   .stream())
        
        if not sets:
            return jsonify({
                'exists': False,
                'stats': None
            })
        
        # Calculate statistics
        total_sets = len(sets)
        available_sets = len([s for s in sets if s.to_dict()['status'] == 'available'])
        sold_sets = len([s for s in sets if s.to_dict()['status'] == 'sold'])
        pending_sets = len([s for s in sets if s.to_dict()['status'] == 'pending_imei'])
        
        total_quantity = sum(s.to_dict()['quantity'] for s in sets)
        available_quantity = sum(s.to_dict()['quantity'] for s in sets if s.to_dict()['status'] == 'available')
        sold_quantity = sum(s.to_dict()['quantity'] for s in sets if s.to_dict()['status'] == 'sold')
        
        # Get product details from first set
        first_set = sets[0].to_dict()
        
        stats = {
            'exists': True,
            'product_info': {
                'itemCode': item_code,
                'productName': first_set['productName'],
                'brand': first_set['brand'],
                'hsnCode': first_set['hsnCode']
            },
            'inventory_stats': {
                'total_sets': total_sets,
                'available_sets': available_sets,
                'sold_sets': sold_sets,
                'pending_sets': pending_sets,
                'total_quantity': total_quantity,
                'available_quantity': available_quantity,
                'sold_quantity': sold_quantity
            },
            'recent_activity': {
                'last_updated': max(s.to_dict().get('updatedAt', s.to_dict().get('createdAt')) for s in sets),
                'last_added': max(s.to_dict().get('createdAt') for s in sets)
            }
        }
        
        return jsonify({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        print(f"Error in get_product_stats: {str(e)}")
        return jsonify({'error': str(e)}), 500

# API Routes for Outward (Cart-based)
@app.route('/api/validate_imei', methods=['POST'])
def validate_imei():
    """Validate IMEI and return product details if found"""
    try:
        data = request.json
        imei = data.get('imei', '').strip()
        
        if not imei:
            return jsonify({'error': 'IMEI is required'}), 400
        
        # Validate IMEI format
        if not imei.isdigit() or len(imei) != 15:
            return jsonify({'error': 'Invalid IMEI format. Must be 15 digits.'}), 400
        
        print(f"Validating IMEI: {imei}")  # Debug log
        
        # Search for IMEI in inventory sets
        sets = db.collection('inventory_sets').where('imeiNumbers', 'array_contains', imei).limit(1).stream()
        
        for set_doc in sets:
            set_data = set_doc.to_dict()
            
            # Check if set is available
            if set_data['status'] != 'available':
                return jsonify({
                    'error': f'IMEI {imei} found but not available for sale. Status: {set_data["status"]}'
                }), 400
            
            # Return product details (no cost information)
            product_data = {
                'setId': set_data['setId'],
                'itemCode': set_data['itemCode'],
                'productName': set_data['productName'],
                'brand': set_data.get('brand', 'Unknown'),
                'hsnCode': set_data.get('hsnCode', ''),
                'quantity': set_data['quantity'],
                'status': set_data['status'],
                'imei': imei,
                'purchaseDetails': set_data.get('purchaseDetails', {})
            }
            
            return jsonify({
                'success': True,
                'product': product_data
            })
        
        # IMEI not found
        return jsonify({
            'error': f'IMEI {imei} not found in inventory. Please check the number and try again.'
        }), 404
        
    except Exception as e:
        print(f"Error in validate_imei: {str(e)}")  # Debug log
        return jsonify({'error': str(e)}), 500

@app.route('/api/search_products', methods=['POST'])
def search_products():
    """Search products by item code or product name"""
    try:
        data = request.json
        search_term = data.get('searchTerm', '').strip().lower()
        
        if not search_term:
            return jsonify({'error': 'Search term is required'}), 400
        
        if len(search_term) < 2:
            return jsonify({'error': 'Search term must be at least 2 characters'}), 400
        
        print(f"Searching for: {search_term}")  # Debug log
        
        # Get all available inventory sets
        available_sets = list(db.collection('inventory_sets').where('status', '==', 'available').stream())
        
        # Group by product and filter by search term
        products = {}
        
        for set_doc in available_sets:
            set_data = set_doc.to_dict()
            item_code = set_data['itemCode']
            product_name = set_data['productName'].lower()
            brand = set_data.get('brand', '').lower()
            
            # Check if search term matches item code, product name, or brand
            if (search_term in item_code.lower() or 
                search_term in product_name or 
                search_term in brand):
                
                if item_code not in products:
                    products[item_code] = {
                        'itemCode': item_code,
                        'productName': set_data['productName'],
                        'brand': set_data.get('brand', 'Unknown'),
                        'hsnCode': set_data.get('hsnCode', ''),
                        'availableSets': 0,
                        'availableQuantity': 0,
                        'availableImeis': []
                    }
                
                products[item_code]['availableSets'] += 1
                products[item_code]['availableQuantity'] += set_data['quantity']
                products[item_code]['availableImeis'].extend(set_data.get('imeiNumbers', []))
        
        # Convert to list and sort by relevance
        products_list = list(products.values())
        
        # Sort by exact match first, then by product name
        def sort_key(product):
            exact_match = search_term == product['itemCode'].lower()
            name_starts_with = product['productName'].lower().startswith(search_term)
            brand_starts_with = product['brand'].lower().startswith(search_term)
            
            return (not exact_match, not name_starts_with, not brand_starts_with, product['productName'])
        
        products_list.sort(key=sort_key)
        
        return jsonify({
            'success': True,
            'products': products_list[:20]  # Limit to 20 results
        })
        
    except Exception as e:
        print(f"Error in search_products: {str(e)}")  # Debug log
        return jsonify({'error': str(e)}), 500

@app.route('/api/get_product_details', methods=['POST'])
def get_product_details():
    """Get detailed product information including all available IMEIs"""
    try:
        data = request.json
        item_code = data.get('itemCode', '').strip()
        
        if not item_code:
            return jsonify({'error': 'Item code is required'}), 400
        
        print(f"Getting product details for: {item_code}")  # Debug log
        
        # Get all available sets for this item code
        available_sets = list(db.collection('inventory_sets')
                            .where('itemCode', '==', item_code)
                           .where(filter=firestore.FieldFilter('status', '==', 'available'))
                            .stream())
        
        if not available_sets:
            return jsonify({'error': f'No available inventory found for item code: {item_code}'}), 404
        
        # Aggregate product information
        first_set = available_sets[0].to_dict()
        all_imeis = []
        total_quantity = 0
        
        for set_doc in available_sets:
            set_data = set_doc.to_dict()
            total_quantity += set_data['quantity']
            all_imeis.extend(set_data.get('imeiNumbers', []))
        
        product_details = {
            'itemCode': item_code,
            'productName': first_set['productName'],
            'brand': first_set.get('brand', 'Unknown'),
            'hsnCode': first_set.get('hsnCode', ''),
            'availableSets': len(available_sets),
            'availableQuantity': total_quantity,
            'availableImeis': all_imeis
        }
        
        return jsonify({
            'success': True,
            'product': product_details
        })
        
    except Exception as e:
        print(f"Error in get_product_details: {str(e)}")  # Debug log
        return jsonify({'error': str(e)}), 500

@app.route('/api/complete_cart_sale', methods=['POST'])
def complete_cart_sale():
    """Complete outward sale for cart-based IMEI sales (no amount calculations)"""
    try:
        data = request.json
        
        # Validate required fields
        required_fields = ['invoiceNumber', 'invoiceDate', 'customerName', 'destination', 'items']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }), 400
        
        # Validate items array
        if not isinstance(data['items'], list) or len(data['items']) == 0:
            return jsonify({
                'success': False,
                'error': 'No items in cart'
            }), 400
        
        invoice_number = data['invoiceNumber']
        invoice_date = data['invoiceDate']
        customer_name = data['customerName']
        destination = data['destination']
        items = data['items']
        
        # Validate each item has required IMEI data
        for item in items:
            required_item_fields = ['imei', 'itemCode', 'productName', 'brand']
            for field in required_item_fields:
                if field not in item or not item[field]:
                    return jsonify({
                        'success': False,
                        'error': f'Missing required item field: {field} for IMEI {item.get("imei", "unknown")}'
                    }), 400
        
        # Check if invoice number already exists
        existing_invoice = db.collection('outward_transactions').where('invoiceNumber', '==', invoice_number).limit(1).get()
        if len(existing_invoice) > 0:
            return jsonify({
                'success': False,
                'error': f'Invoice number {invoice_number} already exists'
            }), 400
        
        # Validate all IMEIs exist and are available
        imei_validation_errors = []
        validated_items = []
        
        for item in items:
            imei = item['imei']
            
            # Check if IMEI exists in inventory
            imei_query = db.collection('inventory_sets').where('imeiNumbers', 'array_contains', imei).limit(1).get()
            
            if not imei_query:
                imei_validation_errors.append(f'IMEI {imei} not found in inventory')
                continue
            
            set_doc = imei_query[0]
            set_data = set_doc.to_dict()
            
            # Check if set is available
            if set_data.get('status') != 'available':
                imei_validation_errors.append(f'IMEI {imei} is not available (set status: {set_data.get("status")})')
                continue
            
            # Add set information to validated item
            validated_item = item.copy()
            validated_item['setId'] = set_doc.id
            validated_item['originalSetData'] = set_data
            validated_items.append(validated_item)
        
        if imei_validation_errors:
            return jsonify({
                'success': False,
                'error': 'IMEI validation failed: ' + '; '.join(imei_validation_errors)
            }), 400
        
        # Process the sale - update inventory
        sold_items = []
        for item in validated_items:
            imei = item['imei']
            set_id = item['setId']
            set_data = item['originalSetData']
            
            # Remove IMEI from the set
            updated_imei_list = [i for i in set_data['imeiNumbers'] if i != imei]
            new_quantity = len(updated_imei_list)
            
            if new_quantity == 0:
                # If no IMEIs left, mark set as sold
                db.collection('inventory_sets').document(set_id).update({
                    'status': 'sold',
                    'imeiNumbers': [],
                    'quantity': 0,
                    'updatedAt': datetime.now()
                })
            else:
                # Update set with remaining IMEIs
                db.collection('inventory_sets').document(set_id).update({
                    'imeiNumbers': updated_imei_list,
                    'quantity': new_quantity,
                    'updatedAt': datetime.now()
                })
            
            # Prepare sold item data (no cost/amount information)
            sold_item = {
                'imei': imei,
                'setId': set_id,
                'itemCode': item['itemCode'],
                'productName': item['productName'],
                'brand': item['brand'],
                'originalSetQuantity': set_data['quantity'],
                'remainingInSet': new_quantity
            }
            sold_items.append(sold_item)
        
        # Create outward transaction record (no amounts)
        transaction_data = {
            'invoiceNumber': invoice_number,
            'invoiceDate': invoice_date,
            'customer': customer_name,
            'destination': destination,
            'items': sold_items,
            'totalQuantity': len(items),
            'saleType': 'imei_based',
            'soldBy': 'admin',  # TODO: Get from session
            'createdAt': datetime.now(),
            'updatedAt': datetime.now()
        }
        
        # Save transaction
        db.collection('outward_transactions').add(transaction_data)
        
        return jsonify({
            'success': True,
            'message': f'Sale completed successfully for {len(items)} phones',
            'invoiceNumber': invoice_number,
            'totalItems': len(items),
            'itemsProcessed': len(sold_items)
        })
    
    except Exception as e:
        print(f"Error in complete_cart_sale: {str(e)}")  # Debug log
        return jsonify({
            'success': False,
            'error': f'Server error: {str(e)}'
        }), 500

# Legacy API Routes (keeping for backward compatibility)
@app.route('/api/scan_qr', methods=['POST'])
def scan_qr():
    """Process QR code scan for outward sales - legacy endpoint"""
    try:
        data = request.json
        scanned_code = data.get('qrCode', '').strip()
        
        if not scanned_code:
            return jsonify({'error': 'QR code is required'}), 400
        
        print(f"Scanning code: {scanned_code}")  # Debug log
        
        # Try different search strategies for sets
        set_doc = None
        search_strategies = []
        
        # Strategy 1: Direct QR code match (QR_SET_631011004416_006)
        if scanned_code.startswith('QR_'):
            search_strategies.append(('qrCode', '==', scanned_code))
        
        # Strategy 2: If it's a set ID format
        if scanned_code.startswith('SET_'):
            search_strategies.append(('setId', '==', scanned_code))
        
        # Strategy 3: If it's just an item code, find available sets
        if not scanned_code.startswith(('QR_', 'SET_')):
            search_strategies.append(('itemCode', '==', scanned_code))
        
        # Strategy 4: Check if it's an IMEI number (15 digits)
        if scanned_code.isdigit() and len(scanned_code) == 15:
            # Search for sets containing this IMEI
            search_strategies.append(('imeiNumbers', 'array_contains', scanned_code))
        
        print(f"Trying {len(search_strategies)} search strategies")  # Debug log
        
        # Try each strategy until we find a match
        for i, (field, operator, value) in enumerate(search_strategies):
            print(f"Strategy {i+1}: Searching {field} {operator} {value}")  # Debug log
            
            if field == 'itemCode':
                # For item code, find the first available set
                sets = db.collection('inventory_sets').where(field, operator, value).where('status', '==', 'available').limit(1).stream()
            else:
                # For other fields, find exact match
                sets = db.collection('inventory_sets').where(field, operator, value).limit(1).stream()
            
            for doc in sets:
                set_doc = doc
                print(f"Found match using strategy {i+1}")  # Debug log
                break
            
            if set_doc:
                break
        
        if not set_doc:
            return jsonify({
                'error': f'No inventory set found for code: {scanned_code}. Please check the code and try again.'
            }), 404
        
        set_data = set_doc.to_dict()
        
        if set_data['status'] != 'available':
            return jsonify({
                'error': f'Set {set_data["setId"]} is not available for sale. Current status: {set_data["status"]}'
            }), 400
        
        # Check if this set has IMEI numbers for individual sales
        has_imei = len(set_data.get('imeiNumbers', [])) > 0
        
        return jsonify({
            'success': True,
            'set_data': {
                'setId': set_data['setId'],
                'itemCode': set_data['itemCode'],
                'productName': set_data['productName'],
                'brand': set_data.get('brand', 'Unknown'),
                'quantity': set_data['quantity'],
                'status': set_data['status'],
                'hasImei': has_imei,
                'imeiNumbers': set_data.get('imeiNumbers', []),
                'scannedCode': scanned_code,
                'purchaseDetails': set_data.get('purchaseDetails', {})
            }
        })
    
    except Exception as e:
        print(f"Error in scan_qr: {str(e)}")  # Debug log
        return jsonify({'error': f'Error processing scan: {str(e)}'}), 500

@app.route('/api/add_imei_to_set', methods=['POST'])
def add_imei_to_set():
    """Add IMEI numbers to an existing set (for sets created without IMEI initially)"""
    try:
        data = request.json
        
        set_id = data.get('setId')
        imei_numbers = data.get('imeiNumbers', [])
        
        if not set_id or not imei_numbers:
            return jsonify({'error': 'Set ID and IMEI numbers are required'}), 400
        
        # Validate IMEI numbers
        is_valid, validation_message = validate_imei_numbers(imei_numbers)
        if not is_valid:
            return jsonify({'error': f'IMEI validation failed: {validation_message}'}), 400
        
        # Get set data
        set_doc = db.collection('inventory_sets').document(set_id).get()
        if not set_doc.exists:
            return jsonify({'error': 'Set not found'}), 404
        
        # Update set with IMEI numbers
        db.collection('inventory_sets').document(set_id).update({
            'imeiNumbers': imei_numbers,
            'status': 'available',  # Change from pending_imei to available
            'updatedAt': datetime.now()
        })
        
        return jsonify({
            'success': True,
            'message': f'Successfully added {len(imei_numbers)} IMEI numbers to set {set_id}'
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Utility API Routes
@app.route('/api/get_invoice_products', methods=['POST'])
def get_invoice_products():
    """Get all products for a specific invoice number"""
    try:
        data = request.json
        invoice_number = data.get('invoiceNumber', '').strip()
        
        if not invoice_number:
            return jsonify({'error': 'Invoice number is required'}), 400
        
        # Get transaction for this invoice
        transactions = list(db.collection('inward_transactions')
                          .where('invoiceNumber', '==', invoice_number)
                          .stream())
        
        if not transactions:
            return jsonify({'error': f'No transaction found for invoice: {invoice_number}'}), 404
        
        transaction_data = transactions[0].to_dict()
        
        return jsonify({
            'success': True,
            'invoice': {
                'invoiceNumber': transaction_data['invoiceNumber'],
                'invoiceDate': transaction_data['invoiceDate'],
                'supplier': transaction_data['supplier'],
                'items': transaction_data.get('items', []),
                'totalQuantity': transaction_data.get('totalQuantity', 0),
                'totalSets': transaction_data.get('totalSets', 0),
                'createdAt': transaction_data['createdAt']
            }
        })
    
    except Exception as e:
        print(f"Error in get_invoice_products: {str(e)}")  # Debug log
        return jsonify({'error': str(e)}), 500

@app.route('/api/get_inventory_summary', methods=['GET'])
def get_inventory_summary():
    """Get inventory summary for dashboard widgets"""
    try:
        # Get all sets
        all_sets = list(db.collection('inventory_sets').stream())
        
        # Group by status
        available_sets = [doc for doc in all_sets if doc.to_dict()['status'] == 'available']
        sold_sets = [doc for doc in all_sets if doc.to_dict()['status'] == 'sold']
        pending_sets = [doc for doc in all_sets if doc.to_dict()['status'] == 'pending_imei']
        
        # Calculate totals
        total_phones_available = sum(doc.to_dict()['quantity'] for doc in available_sets)
        total_phones_sold = sum(doc.to_dict()['quantity'] for doc in sold_sets)
        total_phones_pending = sum(doc.to_dict()['quantity'] for doc in pending_sets)
        
        # Get unique products
        unique_products = set()
        for doc in all_sets:
            data = doc.to_dict()
            unique_products.add(data['itemCode'])
        
        summary = {
            'total_sets': len(all_sets),
            'available_sets': len(available_sets),
            'sold_sets': len(sold_sets),
            'pending_sets': len(pending_sets),
            'total_phones': total_phones_available + total_phones_sold + total_phones_pending,
            'available_phones': total_phones_available,
            'sold_phones': total_phones_sold,
            'pending_phones': total_phones_pending,
            'unique_products': len(unique_products)
        }
        
        return jsonify({
            'success': True,
            'summary': summary
        })
    
    except Exception as e:
        print(f"Error in get_inventory_summary: {str(e)}")  # Debug log
        return jsonify({'error': str(e)}), 500

@app.route('/api/get_sales_summary', methods=['GET'])
def get_sales_summary():
    """Get sales summary for reports"""
    try:
        # Get all outward transactions
        transactions = list(db.collection('outward_transactions').stream())
        
        if not transactions:
            return jsonify({
                'success': True,
                'summary': {
                    'total_transactions': 0,
                    'total_phones_sold': 0,
                    'total_customers': 0,
                    'recent_sales': []
                }
            })
        
        # Calculate summary
        total_phones_sold = sum(trans.to_dict().get('totalQuantity', 0) for trans in transactions)
        customers = set(trans.to_dict().get('customer', 'Unknown') for trans in transactions)
        
        # Get recent sales (last 10)
        recent_transactions = sorted(
            [trans.to_dict() for trans in transactions],
            key=lambda x: x.get('createdAt', datetime.min),
            reverse=True
        )[:10]
        
        summary = {
            'total_transactions': len(transactions),
            'total_phones_sold': total_phones_sold,
            'total_customers': len(customers),
            'recent_sales': recent_transactions
        }
        
        return jsonify({
            'success': True,
            'summary': summary
        })
    
    except Exception as e:
        print(f"Error in get_sales_summary: {str(e)}")  # Debug log
        return jsonify({'error': str(e)}), 500
    


# Add this route to your app.py file

@app.route('/api/submit_multi_product_session', methods=['POST'])
def submit_multi_product_session():
    """Submit complete multi-product session with multiple products under one invoice"""
    try:
        session_data = request.json
        
        # Validate required session fields
        required_session_fields = [
            'invoiceNumber', 'invoiceDate', 'supplierName', 'products',
            'totalProducts', 'totalQuantity', 'totalSets'
        ]
        
        for field in required_session_fields:
            if field not in session_data or not session_data[field]:
                return jsonify({'error': f'Missing required session field: {field}'}), 400
        
        products = session_data['products']
        
        if not isinstance(products, list) or len(products) == 0:
            return jsonify({'error': 'No products in session'}), 400
        
        # Check if invoice number already exists
        existing_invoice = list(db.collection('inward_transactions')
                              .where('invoiceNumber', '==', session_data['invoiceNumber'])
                              .limit(1)
                              .stream())
        
        if existing_invoice:
            return jsonify({'error': f'Invoice number {session_data["invoiceNumber"]} already exists'}), 400
        
        # Validate all products in session
        all_sets_created = []
        processed_items = []
        total_imei_count = 0
        
        for i, product in enumerate(products):
            # Validate product fields
            required_product_fields = [
                'itemCode', 'brand', 'productName', 'hsnCode', 
                'totalQuantity', 'numberOfSets', 'imeiNumbers'
            ]
            
            for field in required_product_fields:
                if field not in product or not product[field]:
                    return jsonify({'error': f'Product {i+1}: Missing required field: {field}'}), 400
            
            # Validate IMEI numbers for this product
            imei_numbers = product['imeiNumbers']
            is_valid, validation_message = validate_imei_numbers(imei_numbers)
            if not is_valid:
                return jsonify({'error': f'Product {i+1} IMEI validation failed: {validation_message}'}), 400
            
            total_imei_count += len(imei_numbers)
        
        # Process each product in the session
        for product in products:
            total_quantity = int(product['totalQuantity'])
            number_of_sets = int(product['numberOfSets'])
            imei_numbers = product['imeiNumbers']
            
            # Create sets for this product
            product_sets_created = []
            
            # Calculate how many complete sets (10 phones each) we can make
            complete_sets = total_quantity // 10
            remaining_phones = total_quantity % 10
            
            # Create complete sets
            for i in range(complete_sets):
                set_number = get_next_set_number(product['itemCode'])
                set_id = f"SET_{product['itemCode']}_{set_number:03d}"
                
                # For the first set, use the scanned IMEI numbers
                if i == 0:
                    set_imeis = imei_numbers
                    set_quantity = 10
                    set_status = 'available'
                else:
                    # Additional sets need IMEI numbers to be added later
                    set_imeis = []
                    set_quantity = 10
                    set_status = 'pending_imei'
                
                set_data = {
                    'setId': set_id,
                    'itemCode': product['itemCode'],
                    'productName': product['productName'],
                    'brand': product['brand'],
                    'hsnCode': product['hsnCode'],
                    'quantity': set_quantity,
                    'status': set_status,
                    'imeiNumbers': set_imeis,
                    'purchaseDetails': {
                        'invoiceNumber': session_data['invoiceNumber'],
                        'invoiceDate': session_data['invoiceDate'],
                        'supplier': session_data['supplierName'],
                        'date': datetime.now().strftime('%Y-%m-%d'),
                        'sessionType': 'multi_product'
                    },
                    'saleDetails': None,
                    'createdAt': datetime.now(),
                    'updatedAt': datetime.now()
                }
                
                db.collection('inventory_sets').document(set_id).set(set_data)
                product_sets_created.append(set_id)
                all_sets_created.append(set_id)
            
            # Create partial set if there are remaining phones
            if remaining_phones > 0:
                set_number = get_next_set_number(product['itemCode'])
                set_id = f"SET_{product['itemCode']}_{set_number:03d}"
                
                partial_set_data = {
                    'setId': set_id,
                    'itemCode': product['itemCode'],
                    'productName': product['productName'],
                    'brand': product['brand'],
                    'hsnCode': product['hsnCode'],
                    'quantity': remaining_phones,
                    'status': 'pending_imei',  # Partial sets need IMEI numbers
                    'imeiNumbers': [],
                    'purchaseDetails': {
                        'invoiceNumber': session_data['invoiceNumber'],
                        'invoiceDate': session_data['invoiceDate'],
                        'supplier': session_data['supplierName'],
                        'date': datetime.now().strftime('%Y-%m-%d'),
                        'sessionType': 'multi_product'
                    },
                    'saleDetails': None,
                    'createdAt': datetime.now(),
                    'updatedAt': datetime.now()
                }
                
                db.collection('inventory_sets').document(set_id).set(partial_set_data)
                product_sets_created.append(set_id)
                all_sets_created.append(set_id)
            
            # Add to processed items
            processed_item = {
                'itemCode': product['itemCode'],
                'productName': product['productName'],
                'brand': product['brand'],
                'hsnCode': product['hsnCode'],
                'totalQuantity': total_quantity,
                'quantityPerSet': 10,
                'setsCreated': len(product_sets_created),
                'completeSets': complete_sets,
                'partialSetPhones': remaining_phones if remaining_phones > 0 else None,
                'isExistingProduct': product.get('isExistingProduct', False),
                'imeiCount': len(imei_numbers)
            }
            processed_items.append(processed_item)
        
        # Create comprehensive inward transaction record
        transaction_data = {
            'invoiceNumber': session_data['invoiceNumber'],
            'invoiceDate': session_data['invoiceDate'],
            'supplier': session_data['supplierName'],
            'items': processed_items,
            'sessionSummary': {
                'totalProducts': session_data['totalProducts'],
                'totalQuantity': session_data['totalQuantity'],
                'totalSets': session_data['totalSets'],
                'totalImeiCount': total_imei_count,
                'sessionCreatedAt': session_data.get('sessionCreatedAt'),
                'entryType': session_data.get('entryType', 'multi_product_session')
            },
            'totalQuantity': session_data['totalQuantity'],
            'totalSets': len(all_sets_created),
            'sets': all_sets_created,
            'imeiCount': total_imei_count,
            'createdBy': 'admin',  # TODO: Get from session/auth
            'createdAt': datetime.now(),
            'entryType': 'multi_product_session'
        }
        
        # Save transaction to database
        transaction_ref = db.collection('inward_transactions').add(transaction_data)
        
        return jsonify({
            'success': True,
            'message': f'Multi-product session submitted successfully! Added {session_data["totalProducts"]} products with {session_data["totalQuantity"]} phones in {len(all_sets_created)} sets',
            'sessionSummary': {
                'invoiceNumber': session_data['invoiceNumber'],
                'totalProducts': session_data['totalProducts'],
                'totalQuantity': session_data['totalQuantity'],
                'totalSets': len(all_sets_created),
                'totalImeiCount': total_imei_count,
                'transactionId': transaction_ref[1].id,
                'setsCreated': all_sets_created,
                'itemsProcessed': processed_items
            }
        })
    
    except Exception as e:
        print(f"Error in submit_multi_product_session: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Session submission failed: {str(e)}'
        }), 500


# Optional: Enhanced validation endpoint for sessions
@app.route('/api/validate_session_products', methods=['POST'])
def validate_session_products():
    """Validate all products in a session before submission"""
    try:
        session_data = request.json
        products = session_data.get('products', [])
        
        if not products:
            return jsonify({'error': 'No products to validate'}), 400
        
        validation_results = []
        total_errors = 0
        
        for i, product in enumerate(products):
            product_result = {
                'productIndex': i,
                'itemCode': product.get('itemCode', ''),
                'productName': product.get('productName', ''),
                'valid': True,
                'errors': [],
                'warnings': []
            }
            
            # Check required fields
            required_fields = ['itemCode', 'brand', 'productName', 'hsnCode', 'totalQuantity', 'imeiNumbers']
            for field in required_fields:
                if field not in product or not product[field]:
                    product_result['errors'].append(f'Missing required field: {field}')
                    product_result['valid'] = False
            
            # Validate IMEI numbers if present
            if 'imeiNumbers' in product and product['imeiNumbers']:
                is_valid, validation_message = validate_imei_numbers(product['imeiNumbers'])
                if not is_valid:
                    product_result['errors'].append(f'IMEI validation: {validation_message}')
                    product_result['valid'] = False
            
            # Check quantities
            try:
                total_qty = int(product.get('totalQuantity', 0))
                if total_qty <= 0:
                    product_result['errors'].append('Total quantity must be greater than 0')
                    product_result['valid'] = False
                elif total_qty % 10 != 0:
                    product_result['warnings'].append(f'Quantity {total_qty} will create partial set with {total_qty % 10} phones')
            except (ValueError, TypeError):
                product_result['errors'].append('Invalid total quantity')
                product_result['valid'] = False
            
            if not product_result['valid']:
                total_errors += 1
            
            validation_results.append(product_result)
        
        return jsonify({
            'success': True,
            'validation': {
                'totalProducts': len(products),
                'validProducts': len(products) - total_errors,
                'invalidProducts': total_errors,
                'canSubmit': total_errors == 0,
                'results': validation_results
            }
        })
    
    except Exception as e:
        print(f"Error in validate_session_products: {str(e)}")
        return jsonify({'error': str(e)}), 500
# Add these new API endpoints to your app.py file (paste-2.txt)

# Add these imports at the top of your app.py file
from datetime import datetime, timedelta
import csv
import io

# Fixed API endpoints - replace the previous ones with these

@app.route('/api/get_daily_summary', methods=['GET'])
def get_daily_summary():
    """Get today's inward/outward summary and current stock levels"""
    try:
        today = datetime.now().date()
        start_of_day = datetime.combine(today, datetime.min.time())
        start_of_tomorrow = datetime.combine(today + timedelta(days=1), datetime.min.time())
        
        # Get today's inward transactions
        today_inward = list(db.collection('inward_transactions')
                           .where(filter=firestore.FieldFilter('createdAt', '>=', start_of_day))
                           .where(filter=firestore.FieldFilter('createdAt', '<', start_of_tomorrow))
                           .stream())
        
        # Get today's outward transactions  
        today_outward = list(db.collection('outward_transactions')
                            .where(filter=firestore.FieldFilter('createdAt', '>=', start_of_day))
                            .where(filter=firestore.FieldFilter('createdAt', '<', start_of_tomorrow))
                            .stream())
        
        # Calculate today's totals
        today_inward_phones = sum(trans.to_dict().get('totalQuantity', 0) for trans in today_inward)
        today_outward_phones = sum(trans.to_dict().get('totalQuantity', 0) for trans in today_outward)
        
        # Get current stock levels
        all_sets = list(db.collection('inventory_sets').stream())
        available_phones = sum(s.to_dict().get('quantity', 0) for s in all_sets if s.to_dict().get('status') == 'available')
        pending_imei_sets = len([s for s in all_sets if s.to_dict().get('status') == 'pending_imei'])
        
        summary = {
            'todayInward': today_inward_phones,
            'todayOutward': today_outward_phones,
            'availableStock': available_phones,
            'pendingIMEI': pending_imei_sets,
            'date': today.isoformat()
        }
        
        return jsonify({
            'success': True,
            'summary': summary
        })
        
    except Exception as e:
        print(f"Error in get_daily_summary: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/get_today_transactions', methods=['GET'])
def get_today_transactions():
    """Get today's inward and outward transactions"""
    try:
        today = datetime.now().date()
        start_of_day = datetime.combine(today, datetime.min.time())
        start_of_tomorrow = datetime.combine(today + timedelta(days=1), datetime.min.time())
        
        # Get today's inward transactions
        inward_query = db.collection('inward_transactions') \
                        .where(filter=firestore.FieldFilter('createdAt', '>=', start_of_day)) \
                        .where(filter=firestore.FieldFilter('createdAt', '<', start_of_tomorrow)) \
                        .order_by('createdAt', direction=firestore.Query.DESCENDING) \
                        .limit(10)
        
        inward_transactions = []
        for doc in inward_query.stream():
            data = doc.to_dict()
            inward_transactions.append({
                'invoiceNumber': data.get('invoiceNumber', ''),
                'supplier': data.get('supplier', ''),
                'totalQuantity': data.get('totalQuantity', 0),
                'totalSets': data.get('totalSets', 0),
                'createdAt': data.get('createdAt')
            })
        
        # Get today's outward transactions
        outward_query = db.collection('outward_transactions') \
                         .where(filter=firestore.FieldFilter('createdAt', '>=', start_of_day)) \
                         .where(filter=firestore.FieldFilter('createdAt', '<', start_of_tomorrow)) \
                         .order_by('createdAt', direction=firestore.Query.DESCENDING) \
                         .limit(10)
        
        outward_transactions = []
        for doc in outward_query.stream():
            data = doc.to_dict()
            outward_transactions.append({
                'invoiceNumber': data.get('invoiceNumber', ''),
                'customer': data.get('customer', ''),
                'totalQuantity': data.get('totalQuantity', 0),
                'createdAt': data.get('createdAt')
            })
        
        return jsonify({
            'success': True,
            'inwardTransactions': inward_transactions,
            'outwardTransactions': outward_transactions
        })
        
    except Exception as e:
        print(f"Error in get_today_transactions: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/get_brand_summary', methods=['GET'])
def get_brand_summary():
    """Get stock summary grouped by brand"""
    try:
        all_sets = list(db.collection('inventory_sets').stream())
        
        brand_summary = {}
        
        for doc in all_sets:
            data = doc.to_dict()
            brand = data.get('brand', 'Unknown')
            status = data.get('status', 'unknown')
            quantity = data.get('quantity', 0)
            
            if brand not in brand_summary:
                brand_summary[brand] = {
                    'brand': brand,
                    'availableSets': 0,
                    'availablePhones': 0,
                    'pendingSets': 0,
                    'totalStock': 0
                }
            
            if status == 'available':
                brand_summary[brand]['availableSets'] += 1
                brand_summary[brand]['availablePhones'] += quantity
                brand_summary[brand]['totalStock'] += quantity
            elif status == 'pending_imei':
                brand_summary[brand]['pendingSets'] += 1
                brand_summary[brand]['totalStock'] += quantity
        
        # Convert to list and sort by total stock
        brand_list = list(brand_summary.values())
        brand_list.sort(key=lambda x: x['totalStock'], reverse=True)
        
        return jsonify({
            'success': True,
            'brandSummary': brand_list
        })
        
    except Exception as e:
        print(f"Error in get_brand_summary: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/export_daily_report', methods=['POST'])
def export_daily_report():
    """Export daily report as CSV"""
    try:
        data = request.json
        report_date = data.get('date', datetime.now().date().isoformat())
        target_date = datetime.strptime(report_date, '%Y-%m-%d').date()
        
        # Get day's transactions
        start_datetime = datetime.combine(target_date, datetime.min.time())
        end_datetime = datetime.combine(target_date + timedelta(days=1), datetime.min.time())
        
        inward_transactions = list(db.collection('inward_transactions')
                                  .where(filter=firestore.FieldFilter('createdAt', '>=', start_datetime))
                                  .where(filter=firestore.FieldFilter('createdAt', '<', end_datetime))
                                  .stream())
        
        outward_transactions = list(db.collection('outward_transactions')
                                   .where(filter=firestore.FieldFilter('createdAt', '>=', start_datetime))
                                   .where(filter=firestore.FieldFilter('createdAt', '<', end_datetime))
                                   .stream())
        
        # Create CSV content
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([f'Daily Inventory Report - {target_date.strftime("%Y-%m-%d")}'])
        writer.writerow([''])
        
        # Summary section
        total_inward = sum(t.to_dict().get('totalQuantity', 0) for t in inward_transactions)
        total_outward = sum(t.to_dict().get('totalQuantity', 0) for t in outward_transactions)
        
        writer.writerow(['SUMMARY'])
        writer.writerow(['Total Inward Phones', total_inward])
        writer.writerow(['Total Outward Phones', total_outward])
        writer.writerow(['Net Movement', total_inward - total_outward])
        writer.writerow([''])
        
        # Inward transactions
        writer.writerow(['INWARD TRANSACTIONS'])
        writer.writerow(['Invoice Number', 'Supplier', 'Quantity', 'Sets', 'Time'])
        for trans in inward_transactions:
            data = trans.to_dict()
            created_at = data.get('createdAt', '')
            time_str = created_at.strftime('%H:%M') if hasattr(created_at, 'strftime') else str(created_at)
            writer.writerow([
                data.get('invoiceNumber', ''),
                data.get('supplier', ''),
                data.get('totalQuantity', 0),
                data.get('totalSets', 0),
                time_str
            ])
        writer.writerow([''])
        
        # Outward transactions
        writer.writerow(['OUTWARD TRANSACTIONS'])
        writer.writerow(['Invoice Number', 'Customer', 'Quantity', 'Time'])
        for trans in outward_transactions:
            data = trans.to_dict()
            created_at = data.get('createdAt', '')
            time_str = created_at.strftime('%H:%M') if hasattr(created_at, 'strftime') else str(created_at)
            writer.writerow([
                data.get('invoiceNumber', ''),
                data.get('customer', ''),
                data.get('totalQuantity', 0),
                time_str
            ])
        
        # Create response
        csv_content = output.getvalue()
        output.close()
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=daily_report_{report_date}.csv'
        
        return response
        
    except Exception as e:
        print(f"Error in export_daily_report: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500    
# Health check endpoint
@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        db.collection('inventory_sets').limit(1).get()
        
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'database': 'connected'
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'timestamp': datetime.now().isoformat(),
            'database': 'disconnected',
            'error': str(e)
        }), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)