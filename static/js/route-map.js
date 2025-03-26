/**
 * Rota Optimizasyon Uygulaması - Ortak Harita Fonksiyonları
 * Bu dosya, şirket ve sürücü panellerinde kullanılan ortak harita fonksiyonlarını içerir.
 */

// Global değişkenler
let routeMap = null;
let routeMarkers = [];
let routePolylines = [];

/**
 * Durum rengini döndürür
 * @param {string} status - Durum kodu
 * @returns {string} - Renk kodu
 */
function getStatusColor(status) {
    switch (status) {
        case 'completed': return '#198754';  // success
        case 'failed': return '#dc3545';     // danger
        case 'skipped': return '#6c757d';    // secondary
        default: return '#0d6efd';           // primary
    }
}

/**
 * Durum metni döndürür
 * @param {string} status - Durum kodu
 * @returns {string} - Durum metni
 */
function getStatusText(status) {
    switch (status) {
        case 'planned': return 'Planlandı';
        case 'in_progress': return 'Devam Ediyor';
        case 'completed': return 'Tamamlandı';
        case 'failed': return 'Başarısız';
        case 'skipped': return 'Atlandı';
        case 'cancelled': return 'İptal Edildi';
        default: return status;
    }
}

/**
 * Durum badge rengi döndürür
 * @param {string} status - Durum kodu
 * @returns {string} - Badge renk sınıfı
 */
function getStatusBadgeColor(status) {
    switch (status) {
        case 'completed': return 'success';
        case 'in_progress': return 'warning';
        case 'failed': return 'danger';
        case 'skipped': return 'secondary';
        case 'cancelled': return 'danger';
        default: return 'info';
    }
}

/**
 * Rota detaylarını gösterir
 * @param {number} routeId - Rota ID
 * @param {string} modalId - Modal element ID
 * @param {string} mapId - Harita container ID
 * @param {string} infoId - Bilgi container ID
 * @param {string} stopsId - Duraklar container ID (opsiyonel)
 * @param {boolean} isDriverView - Sürücü görünümü mü?
 */
function showRouteDetails(routeId, modalId, mapId, infoId, stopsId, isDriverView = false) {
    // Mevcut haritayı temizle
    const mapContainer = document.getElementById(mapId);
    if (window.currentRouteMap) {
        window.currentRouteMap.remove();
        window.currentRouteMap = null;
    }

    // Harita container'ını sıfırla
    mapContainer.innerHTML = '';
        
    fetch(`/api/route/${routeId}`)
        .then(response => response.json())
        .then(data => {
            // API yanıtı artık doğrudan data objesi olarak geliyor, success.data yapısı yok
            // Debug: API yanıtını kontrol et
            console.log('Route API Response:', data);
            console.log('Driver Info:', data.driver);
            console.log('Vehicle Info:', data.vehicle);
            console.log('Total Distance:', data.total_distance);
            
            const modal = new bootstrap.Modal(document.getElementById(modalId));
            
            // Haritayı oluştur
            const map = L.map(mapId, {
                preferCanvas: true,
                renderer: L.canvas(),
                zoomControl: true,
                minZoom: 4,
                maxZoom: 18
            });
            
            window.currentRouteMap = map;
            
            // Tile layer'ı ekle
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '© OpenStreetMap contributors',
                maxZoom: 18,
                tileSize: 256,
                zoomOffset: 0
            }).addTo(map);

            // Rota katmanını oluştur
            const routeLayer = L.featureGroup().addTo(map);
            let bounds = L.latLngBounds();
            
            // Önce depo noktasını ekle
            if (data.warehouse) {
                const depotMarker = createMarker(data.warehouse, 'D', true);
                routeLayer.addLayer(depotMarker);
                bounds.extend([data.warehouse.latitude, data.warehouse.longitude]);
            }
                
            // Müşteri noktalarını ekle
            data.stops.forEach((stop, index) => {
                if (!stop.customer || !stop.customer.latitude || !stop.customer.longitude) {
                    console.warn('Invalid customer data:', stop);
                    return;
                }
                
                // Müşteri marker'ını ekle
                const marker = createMarker(stop.customer, index + 1, false);
                routeLayer.addLayer(marker);
                bounds.extend([stop.customer.latitude, stop.customer.longitude]);
            });
            
            // Rota çizgilerini ekle
            if (data.warehouse && data.stops.length > 0) {
                // Eğer route_geometries varsa, bunları kullan
                if (data.route_geometries && data.route_geometries.length > 0) {
                    console.log('Using route geometries from API:', data.route_geometries);
                    // Her segment için geometri verilerini kullan
                    data.route_geometries.forEach(segment => {
                        if (segment.coordinates && segment.coordinates.length > 0) {
                            // OSRM'den gelen koordinatları Leaflet formatına dönüştür
                            const coords = segment.coordinates.map(coord => [coord[1], coord[0]]);
                            const polyline = L.polyline(coords, {
                                color: '#0d6efd',
                                weight: 3,
                                opacity: 0.8
                            });
                            routeLayer.addLayer(polyline);
                            
                            // Sınırları genişlet
                            coords.forEach(coord => bounds.extend(coord));
                        }
                    });
                } else {
                    console.log('No route geometries found, using straight lines');
                    // Geometri verisi yoksa düz çizgiler kullan
                    // Depodan ilk müşteriye
                    const firstCustomer = data.stops[0].customer;
                    const firstLine = createRoutePolyline([
                        [data.warehouse.latitude, data.warehouse.longitude],
                        [firstCustomer.latitude, firstCustomer.longitude]
                    ]);
                    routeLayer.addLayer(firstLine);

                    // Müşteriler arası
                    for (let i = 0; i < data.stops.length - 1; i++) {
                        const start = data.stops[i].customer;
                        const end = data.stops[i + 1].customer;
                        
                        if (!start || !end || !start.latitude || !start.longitude || !end.latitude || !end.longitude) {
                            console.warn('Invalid coordinates for route segment:', i);
                            continue;
                        }
                        
                        const coords = [[start.latitude, start.longitude], [end.latitude, end.longitude]];
                        const polyline = createRoutePolyline(coords);
                        routeLayer.addLayer(polyline);
                    }

                    // Son müşteriden depoya
                    const lastCustomer = data.stops[data.stops.length - 1].customer;
                    const lastLine = createRoutePolyline([
                        [lastCustomer.latitude, lastCustomer.longitude],
                        [data.warehouse.latitude, data.warehouse.longitude]
                    ]);
                    routeLayer.addLayer(lastLine);
                }
            }
            
            // Haritayı ayarla ve sınırlara göre yakınlaştır
            if (bounds.isValid()) {
                try {
                    map.fitBounds(bounds, {
                        padding: [50, 50],
                        maxZoom: 15,
                        animate: true,
                        duration: 1
                    });
                } catch (e) {
                    console.error('Error fitting bounds:', e);
                    map.setView([39.9334, 32.8597], 6);
                }
            } else {
                console.warn('Invalid bounds, using default view');
                map.setView([39.9334, 32.8597], 6);
            }

            // Harita yüklendikten sonra zoom kontrollerini güncelle
            map.on('load', function() {
                if (!map.zoomControl) {
                    L.control.zoom({
                        position: 'topleft'
                    }).addTo(map);
                }
            });

            // Rota bilgilerini göster
            updateRouteInfo(data, infoId, isDriverView);
            
            // Modalı göster
            modal.show();

            // Modal gösterildikten sonra haritayı yeniden boyutlandır
            modal.handleUpdate();
            setTimeout(() => {
                map.invalidateSize();
                if (bounds.isValid()) {
                    map.fitBounds(bounds, {padding: [50, 50]});
                }
            }, 250);
        })
        .catch(error => {
            console.error('Error loading route details:', error);
            alert('Rota detayları yüklenirken bir hata oluştu: ' + error.message);
        });
}

function createMarker(point, label, isDepot = false) {
    const markerColor = isDepot ? '#dc3545' : '#0d6efd';
    const markerSize = isDepot ? 32 : 24;
    const fontSize = isDepot ? 14 : 12;
    
    const markerHtml = `
        <div style="
            background-color: ${markerColor};
            border: 2px solid white;
            border-radius: 50%;
            width: ${markerSize}px;
            height: ${markerSize}px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
            font-size: ${fontSize}px;
        ">
            ${label}
        </div>
    `;
    
    const marker = L.marker([point.latitude, point.longitude], {
        icon: L.divIcon({
            className: isDepot ? 'depot-marker' : 'customer-marker',
            html: markerHtml
        })
    });
    
    // Popup içeriği
    const popupContent = `
        <div class="route-stop-popup">
            <h6>${point.name}</h6>
            <p class="mb-2">${point.address}</p>
            ${point.contact_person ? `
                <div class="contact-info mb-2">
                    <small>
                        <i class="bi bi-person"></i> ${point.contact_person}<br>
                        <i class="bi bi-telephone"></i> ${point.contact_phone}
                    </small>
                </div>
            ` : ''}
        </div>
    `;
    
    marker.bindPopup(popupContent);
    return marker;
}

function createRoutePolyline(coordinates) {
    const options = {
        color: '#0d6efd',
        weight: 3,
        opacity: 0.8
    };
    
    return L.polyline(coordinates, options);
}

function getStatusBadge(status) {
    const statusMap = {
        'planned': ['secondary', 'Planlandı'],
        'in_progress': ['primary', 'Devam Ediyor'],
        'completed': ['success', 'Tamamlandı'],
        'failed': ['danger', 'Başarısız'],
        'cancelled': ['danger', 'İptal Edildi'],
        'skipped': ['warning', 'Atlandı']
    };
    
    const [color, text] = statusMap[status] || ['secondary', status];
    return `<span class="badge bg-${color}">${text}</span>`;
}

function getStopActionButtons(routeId, stop) {
    const buttons = [];
    
    if (stop.status === 'pending') {
        buttons.push(`
            <button class="btn btn-success complete-stop" 
                    data-route="${routeId}" data-stop="${stop.id}">
                <i class="bi bi-check-lg"></i>
            </button>
        `);
        buttons.push(`
            <button class="btn btn-danger fail-stop"
                    data-route="${routeId}" data-stop="${stop.id}">
                <i class="bi bi-x-lg"></i>
            </button>
        `);
    }
    
    buttons.push(`
        <button class="btn btn-info note-btn" title="Not Ekle"
                data-route="${routeId}" data-stop="${stop.id}">
            <i class="bi bi-pencil"></i>
        </button>
    `);
    
    return buttons.join('');
}

/**
 * Durak durumunu günceller
 */
function updateStopStatus(routeId, stopId, newStatus) {
    // Remove the automatic note prompt
    console.log(`Updating stop status - Route: ${routeId}, Stop: ${stopId}, Status: ${newStatus}`);
    
    // Disable all buttons for this stop to prevent multiple clicks
    const stopButtons = document.querySelectorAll(`button[data-stop-id="${stopId}"]`);
    stopButtons.forEach(button => {
        button.disabled = true;
        button.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> İşleniyor...';
    });
    
    fetch(`/api/route/${routeId}/stop/${stopId}/status`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        },
        body: JSON.stringify({
            status: newStatus,
            notes: null // No notes by default
        })
    })
    .then(response => {
        console.log('Response status:', response.status);
        console.log('Response headers:', response.headers);
        
        if (!response.ok) {
            if (response.status === 404) {
                throw new Error('Durak veya rota bulunamadı');
            }
            throw new Error('API yanıtı başarısız: ' + response.status);
        }
        
        return response.json().catch(error => {
            console.error('JSON parse error:', error);
            throw new Error('API yanıtı JSON formatında değil');
        });
    })
    .then(data => {
        if (data.success) {
            // Aynı modal içinde rota detaylarını yeniden göster
            showRouteDetails(routeId, 'routeDetailsModal', 'routeMap', 'routeInfo', 'routeStops', true);
        } else {
            alert('Hata: ' + (data.error || 'Bilinmeyen bir hata oluştu'));
            // Re-enable buttons if there was an error
            stopButtons.forEach(button => {
                button.disabled = false;
                if (button.dataset.status === 'completed') {
                    button.innerHTML = '<i class="bi bi-check-lg"></i> Tamamlandı';
                } else if (button.dataset.status === 'failed') {
                    button.innerHTML = '<i class="bi bi-x-lg"></i> Başarısız';
                }
            });
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Hata: ' + error.message);
        // Re-enable buttons if there was an error
        stopButtons.forEach(button => {
            button.disabled = false;
            if (button.dataset.status === 'completed') {
                button.innerHTML = '<i class="bi bi-check-lg"></i> Tamamlandı';
            } else if (button.dataset.status === 'failed') {
                button.innerHTML = '<i class="bi bi-x-lg"></i> Başarısız';
            }
        });
    });
}

/**
 * Durak notu ekler
 */
function addStopNote(routeId, stopId) {
    const notes = prompt('Bu durak için not ekleyin:');
    if (notes === null) return; // User cancelled
    
    fetch(`/api/route/${routeId}/stop/${stopId}/note`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        },
        body: JSON.stringify({
            notes: notes
        })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('API yanıtı başarısız: ' + response.status);
        }
        return response.json();
    })
    .then(data => {
        if (data.success) {
            alert('Not başarıyla eklendi.');
            // Refresh the route details
            showRouteDetails(routeId, 'routeDetailsModal', 'routeMap', 'routeInfo', 'routeStops', true);
        } else {
            alert('Hata: ' + (data.error || 'Bilinmeyen bir hata oluştu'));
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Hata: ' + error.message);
    });
}

/**
 * Rota durumunu günceller
 */
function updateRouteStatus(routeId, newStatus) {
    if (!confirm(`Rota durumunu "${getStatusText(newStatus)}" olarak güncellemek istediğinizden emin misiniz?`)) {
        return;
    }
    
    fetch(`/api/route/${routeId}/status`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ status: newStatus })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            location.reload();
        } else {
            alert('Hata: ' + (data.error || 'Bilinmeyen bir hata oluştu'));
        }
    })
    .catch(error => {
        alert('Hata: ' + error.message);
    });
}

/**
 * Tarih/saat formatlar
 */
function formatDateTime(dateStr) {
    if (!dateStr) return null;
    const date = new Date(dateStr);
    return date.toLocaleString('tr-TR', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

/**
 * Süre formatlar
 */
function formatDuration(minutes) {
    if (!minutes) return '-';
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return `${hours}s ${mins}dk`;
}

function updateRouteInfo(data, infoId, isDriverView) {
    const routeInfo = document.getElementById(infoId);
    
    // Debug: Gelen verileri kontrol et
    console.log('UpdateRouteInfo Data:', {
        driver: data.driver,
        vehicle: data.vehicle,
        total_distance: data.total_distance,
        total_demand: data.total_demand
    });
    
    // Araç bilgisini hazırla
    let vehicleInfo = 'Atanmamış';
    if (data.vehicle && data.vehicle.plate_number) {
        vehicleInfo = `${data.vehicle.brand || ''} ${data.vehicle.model || ''} - ${data.vehicle.plate_number}`.trim();
    }
    
    // Şoför bilgisini hazırla
    let driverInfo = 'Atanmamış';
    if (data.driver && data.driver.user) {
        driverInfo = `${data.driver.user.first_name || ''} ${data.driver.user.last_name || ''}`.trim();
    }
    
    // Mesafe hesaplama
    let distance = 0;
    if (typeof data.total_distance === 'string') {
        distance = parseFloat(data.total_distance);
    } else if (typeof data.total_distance === 'number') {
        distance = data.total_distance;
    }
    
    routeInfo.innerHTML = `
        <div class="route-details">
            <h6>Rota Bilgileri</h6>
            <div class="row">
                <div class="col-md-12">
                    <p>
                        <strong>Durum:</strong> ${getStatusBadge(data.status)}<br>
                        <strong>Araç:</strong> ${vehicleInfo}<br>
                        <strong>Şoför:</strong> ${driverInfo}<br>
                        <strong>Toplam Mesafe:</strong> ${distance ? distance.toFixed(1) : '0.0'} km<br>
                        <strong>Toplam Yük:</strong> ${data.total_demand ? data.total_demand.toFixed(2) : '0.00'} desi<br>
                        <strong>Durak Sayısı:</strong> ${data.stops.length} müşteri
                    </p>
                </div>
            </div>

            ${isDriverView ? `
                <div class="route-actions mt-3">
                    <h6>Rota Durumu</h6>
                    <div class="btn-group">
                        <button class="btn btn-sm status-btn btn-primary update-route-status" 
                                data-route-id="${data.id}" 
                                data-status="in_progress"
                                ${data.status === 'in_progress' ? 'disabled' : ''}>
                            <i class="bi bi-play-fill"></i> Başlat
                        </button>
                        <button class="btn btn-sm status-btn btn-success update-route-status" 
                                data-route-id="${data.id}" 
                                data-status="completed"
                                ${data.status === 'completed' ? 'disabled' : ''}>
                            <i class="bi bi-check-lg"></i> Tamamlandı
                        </button>
                        <button class="btn btn-sm status-btn btn-warning update-route-status" 
                                data-route-id="${data.id}" 
                                data-status="cancelled"
                                ${data.status === 'cancelled' ? 'disabled' : ''}>
                            <i class="bi bi-x-lg"></i> İptal Et
                        </button>
                    </div>
                </div>
            ` : ''}
            
            <div class="route-stops mt-4">
                <h6>Duraklar (${data.stops.length})</h6>
                ${data.stops.map((stop, index) => `
                    <div class="route-stop">
                        <div class="d-flex justify-content-between align-items-center">
                            <div>
                                <strong>${index + 1}. ${stop.customer?.name || ''}</strong>
                                <br>
                                <small>${stop.customer?.address || ''}</small>
                                ${stop.planned_arrival ? `
                                    <br>
                                    <small class="text-muted">
                                        <i class="bi bi-clock"></i> 
                                        Planlanan: ${formatDateTime(stop.planned_arrival)}
                                    </small>
                                ` : ''}
                            </div>
                            ${isDriverView ? `
                                <div class="btn-group btn-group-sm">
                                    ${getStopActionButtons(data.id, stop)}
                                </div>
                            ` : ''}
                        </div>

                        <div class="stop-details mt-2">
                            <small>
                                <i class="bi bi-geo-alt"></i> ${stop.customer?.address || ''}<br>
                                <i class="bi bi-box"></i> Yük: ${(stop.demand || 0).toFixed(2)} desi
                            </small>
                        </div>

                        ${stop.notes ? `
                            <div class="stop-notes mt-2">
                                <small class="text-info">
                                    <i class="bi bi-journal-text"></i> ${stop.notes}
                                </small>
                            </div>
                        ` : ''}
                    </div>
                `).join('')}
            </div>
        </div>
    `;

    // Event listener'ları ekle
    if (isDriverView) {
        addEventListeners(data.id);
    }
}

function addEventListeners(routeId) {
    // Rota durumu butonları
    document.querySelectorAll('.update-route-status').forEach(button => {
        button.addEventListener('click', function() {
            updateRouteStatus(
                this.dataset.routeId,
                this.dataset.status
            );
        });
    });

    // Durak durumu butonları
    document.querySelectorAll('.complete-stop, .fail-stop').forEach(button => {
        button.addEventListener('click', function() {
            const status = this.classList.contains('complete-stop') ? 'completed' : 'failed';
            updateStopStatus(
                this.dataset.route,
                this.dataset.stop,
                status
            );
        });
    });

    // Not ekleme butonları
    document.querySelectorAll('.note-btn').forEach(button => {
        button.addEventListener('click', function() {
            addStopNote(
                this.dataset.route,
                this.dataset.stop
            );
        });
    });
}

// Modal kapatıldığında haritayı temizle
document.addEventListener('hidden.bs.modal', function(event) {
    if (window.currentRouteMap) {
        window.currentRouteMap.remove();
        window.currentRouteMap = null;
    }
}); 