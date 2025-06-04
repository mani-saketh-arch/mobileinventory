// AS Mobiles Inventory - JavaScript Functions

// Global variables
let qrScanner = null;
let isScanning = false;

// Utility Functions
function showLoading(buttonId) {
    const button = document.getElementById(buttonId);
    if (button) {
        button.disabled = true;
        button.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Processing...';
    }
}

function hideLoading(buttonId, originalText) {
    const button = document.getElementById(buttonId);
    if (button) {
        button.disabled = false;
        button.innerHTML = originalText;
    }
}

function showAlert(message, type = 'success') {
    const alertHtml = `
        <div class="alert alert-${type} alert-dismissible fade show" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    
    // Insert at the top of the container
    const container = document.querySelector('.container');
    const firstChild = container.firstElementChild;
    const alertDiv = document.createElement('div');
    alertDiv.innerHTML = alertHtml;
    container.insertBefore(alertDiv, firstChild);
    
    // Auto-hide after 5 seconds
    setTimeout(() => {
        const alert = alertDiv.querySelector('.alert');
        if (alert) {
            alert.remove();
        }
    }, 5000);
}

// Inward Entry Functions
function calculateSets() {
    const totalQty = parseInt(document.getElementById('totalQuantity').value) || 0;
    const qtyPerSet = parseInt(document.getElementById('quantityPerSet').value) || 10;
    
    if (totalQty > 0 && qtyPerSet > 0) {
        const completeSets = Math.floor(totalQty / qtyPerSet);
        const remainingPhones = totalQty % qtyPerSet;
        
        let resultText = `${completeSets} complete sets of ${qtyPerSet} phones`;
        if (remainingPhones > 0) {
            resultText += ` + 1 set of ${remainingPhones} phones`;
        }
        
        document.getElementById('setsCalculation').innerHTML = `
            <div class="alert alert-info">
                <strong>Sets to be created:</strong> ${resultText}
                <br><strong>Total sets:</strong> ${completeSets + (remainingPhones > 0 ? 1 : 0)}
            </div>
        `;
    } else {
        document.getElementById('setsCalculation').innerHTML = '';
    }
}

async function submitInwardForm() {
    const formData = {
        itemCode: document.getElementById('itemCode').value,
        totalQuantity: document.getElementById('totalQuantity').value,
        quantityPerSet: document.getElementById('quantityPerSet').value,
        invoiceNumber: document.getElementById('invoiceNumber').value,
        supplier: document.getElementById('supplier').value,
        costPrice: document.getElementById('costPrice').value
    };
    
    // Validate form
    for (const [key, value] of Object.entries(formData)) {
        if (!value) {
            showAlert(`Please fill in ${key.replace(/([A-Z])/g, ' $1').toLowerCase()}`, 'danger');
            return;
        }
    }
    
    showLoading('submitInwardBtn');
    
    try {
        const response = await fetch('/api/add_inward', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(formData)
        });
        
        const result = await response.json();
        
        if (result.success) {
            showAlert(`Successfully created ${result.sets_created.length} sets with ${result.total_quantity} phones!`, 'success');
            
            // Show created sets
            let setsHtml = '<h5>Sets Created:</h5><ul>';
            result.sets_created.forEach(setId => {
                setsHtml += `<li><strong>${setId}</strong></li>`;
            });
            setsHtml += '</ul>';
            
            document.getElementById('createdSets').innerHTML = setsHtml;
            
            // Reset form
            document.getElementById('inwardForm').reset();
            document.getElementById('setsCalculation').innerHTML = '';
            
        } else {
            showAlert(result.error || 'Error creating sets', 'danger');
        }
    } catch (error) {
        showAlert('Network error: ' + error.message, 'danger');
    } finally {
        hideLoading('submitInwardBtn', '<i class="fas fa-plus me-2"></i>Create Sets');
    }
}

// QR Scanner Functions
async function startQRScanner() {
    const video = document.getElementById('qr-video');
    const resultDiv = document.getElementById('qr-result');
    
    if (!video) return;
    
    try {
        // Request camera permission
        const stream = await navigator.mediaDevices.getUserMedia({ 
            video: { facingMode: 'environment' } // Use back camera if available
        });
        
        video.srcObject = stream;
        video.style.display = 'block';
        isScanning = true;
        
        // Start scanning
        scanQRCode();
        
        document.getElementById('startScanBtn').style.display = 'none';
        document.getElementById('stopScanBtn').style.display = 'inline-block';
        
    } catch (error) {
        showAlert('Camera access denied or not available: ' + error.message, 'danger');
        console.error('Camera error:', error);
    }
}

function stopQRScanner() {
    const video = document.getElementById('qr-video');
    
    if (video && video.srcObject) {
        video.srcObject.getTracks().forEach(track => track.stop());
        video.style.display = 'none';
    }
    
    isScanning = false;
    
    document.getElementById('startScanBtn').style.display = 'inline-block';
    document.getElementById('stopScanBtn').style.display = 'none';
}

function scanQRCode() {
    const video = document.getElementById('qr-video');
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    
    function tick() {
        if (!isScanning) return;
        
        if (video.readyState === video.HAVE_ENOUGH_DATA) {
            canvas.height = video.videoHeight;
            canvas.width = video.videoWidth;
            context.drawImage(video, 0, 0, canvas.width, canvas.height);
            
            const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
            
            // Try to decode QR code (this is a simplified version)
            // In a real implementation, you'd use a library like jsQR
            
            // For demo purposes, we'll simulate QR detection on click
            video.onclick = function() {
                // Simulate scanning our test QR code
                processQRResult('QR_SET_631011004424_001');
            };
        }
        
        requestAnimationFrame(tick);
    }
    
    tick();
}

async function processQRResult(qrCode) {
    if (!qrCode) return;
    
    stopQRScanner();
    
    try {
        const response = await fetch('/api/scan_qr', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ qrCode: qrCode })
        });
        
        const result = await response.json();
        
        if (result.success) {
            const setData = result.set_data;
            
            // Show set details
            document.getElementById('qr-result').innerHTML = `
                <div class="alert alert-success">
                    <h5><i class="fas fa-check-circle me-2"></i>Set Found!</h5>
                    <p><strong>Set ID:</strong> ${setData.setId}</p>
                    <p><strong>Product:</strong> ${setData.productName}</p>
                    <p><strong>Quantity:</strong> ${setData.quantity} phones</p>
                    <p><strong>Status:</strong> ${setData.status}</p>
                    <button class="btn btn-primary" onclick="showSaleForm('${setData.setId}', '${setData.productName}', ${setData.quantity})">
                        <i class="fas fa-shopping-cart me-2"></i>Proceed to Sale
                    </button>
                </div>
            `;
        } else {
            document.getElementById('qr-result').innerHTML = `
                <div class="alert alert-danger">
                    <h5><i class="fas fa-times-circle me-2"></i>Error</h5>
                    <p>${result.error}</p>
                </div>
            `;
        }
    } catch (error) {
        showAlert('Error processing QR code: ' + error.message, 'danger');
    }
}

function showSaleForm(setId, productName, quantity) {
    document.getElementById('sale-form').style.display = 'block';
    document.getElementById('sale-setId').value = setId;
    document.getElementById('sale-productName').value = productName;
    document.getElementById('sale-quantity').value = quantity;
    
    // Scroll to form
    document.getElementById('sale-form').scrollIntoView({ behavior: 'smooth' });
}

async function completeSale() {
    const formData = {
        setId: document.getElementById('sale-setId').value,
        customer: document.getElementById('sale-customer').value,
        invoiceNumber: document.getElementById('sale-invoiceNumber').value,
        sellingPrice: document.getElementById('sale-sellingPrice').value,
        destination: document.getElementById('sale-destination').value
    };
    
    // Validate form
    for (const [key, value] of Object.entries(formData)) {
        if (!value) {
            showAlert(`Please fill in ${key.replace(/([A-Z])/g, ' $1').toLowerCase()}`, 'danger');
            return;
        }
    }
    
    showLoading('completeSaleBtn');
    
    try {
        const response = await fetch('/api/complete_sale', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(formData)
        });
        
        const result = await response.json();
        
        if (result.success) {
            showAlert(result.message, 'success');
            
            // Reset forms
            document.getElementById('sale-form').style.display = 'none';
            document.getElementById('qr-result').innerHTML = '';
            document.querySelectorAll('#sale-form input').forEach(input => input.value = '');
            
        } else {
            showAlert(result.error || 'Error completing sale', 'danger');
        }
    } catch (error) {
        showAlert('Network error: ' + error.message, 'danger');
    } finally {
        hideLoading('completeSaleBtn', '<i class="fas fa-check me-2"></i>Complete Sale');
    }
}

// Manual QR Entry (for testing)
function testQRScan() {
    const qrInput = document.getElementById('manual-qr-input');
    if (qrInput && qrInput.value) {
        processQRResult(qrInput.value);
    }
}

// Search and Filter Functions
function searchInventory() {
    const searchTerm = document.getElementById('inventorySearch').value.toLowerCase();
    const rows = document.querySelectorAll('.inventory-row');
    
    rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        if (text.includes(searchTerm)) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
        }
    });
}

function filterByStatus(status) {
    const rows = document.querySelectorAll('.inventory-row');
    
    rows.forEach(row => {
        const statusCell = row.querySelector('.status-cell');
        if (status === 'all' || statusCell.textContent.toLowerCase().includes(status)) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
        }
    });
}

// Initialize page-specific functions
document.addEventListener('DOMContentLoaded', function() {
    // Add event listeners for inward form
    const totalQtyInput = document.getElementById('totalQuantity');
    const qtyPerSetInput = document.getElementById('quantityPerSet');
    
    if (totalQtyInput && qtyPerSetInput) {
        totalQtyInput.addEventListener('input', calculateSets);
        qtyPerSetInput.addEventListener('input', calculateSets);
    }
    
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
});