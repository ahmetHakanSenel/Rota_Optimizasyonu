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
    // Mevcut event listener'ları temizle
    const modalElement = document.getElementById(modalId);
    const newModalElement = modalElement.cloneNode(true);
    modalElement.parentNode.replaceChild(newModalElement, modalElement);
    
    // Modal'ı göster
    const modal = new bootstrap.Modal(document.getElementById(modalId));
    modal.show();
    
    // Harita ve marker değişkenleri
    let routeMap = null;
    let routeMarkers = [];
    let routePolylines = [];
    
    // Modal gösterildiğinde haritayı oluştur
    document.getElementById(modalId).addEventListener('shown.bs.modal', function () {
        // Harita container'ını temizle
        const mapContainer = document.getElementById(mapId);
        mapContainer.innerHTML = '';
        
        // Haritayı oluştur
        routeMap = L.map(mapId).setView([39.9334, 32.8597], 10);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        }).addTo(routeMap);
        
        // Haritanın boyutunu güncelle
        setTimeout(() => {
            routeMap.invalidateSize();
        }, 300);
        
        // Rota verilerini getir
        fetch(`/api/route/${routeId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! Status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                console.log("Route data received:", data);
                const bounds = L.latLngBounds();
                
                // Depo
                if (data.warehouse) {
                    const depot = L.marker(
                        [data.warehouse.latitude, data.warehouse.longitude],
                        {
                            icon: L.divIcon({
                                className: 'depot-marker',
                                html: '<div style="background-color: #198754; width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; border: 2px solid white;">D</div>'
                            })
                        }
                    ).bindPopup(`
                        <strong>${data.warehouse.name}</strong><br>
                        ${data.warehouse.address}
                    `);
                    
                    routeMarkers.push(depot);
                    depot.addTo(routeMap);
                    bounds.extend([data.warehouse.latitude, data.warehouse.longitude]);
                }
                
                // Duraklar
                if (data.stops && data.stops.length > 0) {
                    data.stops.forEach((stop, index) => {
                        const marker = L.marker(
                            [stop.customer.latitude, stop.customer.longitude],
                            {
                                icon: L.divIcon({
                                    className: 'customer-marker',
                                    html: `<div style="background-color: ${getStatusColor(stop.status)}; width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; border: 2px solid white;">${index + 1}</div>`
                                })
                            }
                        ).bindPopup(`
                            <strong>${stop.customer.name}</strong><br>
                            ${stop.customer.address}<br>
                            <small>
                                <strong>İletişim:</strong> ${stop.customer.contact_person}<br>
                                <strong>Telefon:</strong> ${stop.customer.contact_phone}<br>
                                <strong>Desi:</strong> ${stop.demand}<br>
                                <strong>Durum:</strong> ${getStatusText(stop.status)}
                            </small>
                        `);
                        
                        routeMarkers.push(marker);
                        marker.addTo(routeMap);
                        bounds.extend([stop.customer.latitude, stop.customer.longitude]);
                    });
                }
                
                // Haritayı sınırlara göre ayarla
                if (routeMarkers.length > 0) {
                    routeMap.fitBounds(bounds, { padding: [50, 50] });
                    routeMap.invalidateSize();
                }
                
                // Rota çizgilerini çiz
                if (data.warehouse && data.stops && data.stops.length > 0) {
                    // Tüm noktaları bir diziye ekle (depo -> duraklar -> depo)
                    const points = [
                        [data.warehouse.latitude, data.warehouse.longitude],
                        ...data.stops.map(stop => [stop.customer.latitude, stop.customer.longitude]),
                        [data.warehouse.latitude, data.warehouse.longitude]
                    ];
                    
                    // Tüm rotayı tek bir polyline olarak çiz
                    const polyline = L.polyline(points, {
                        color: '#0d6efd',
                        weight: 3,
                        opacity: 0.8,
                        dashArray: '5, 10'
                    }).addTo(routeMap);
                    
                    routePolylines.push(polyline);
                }
                
                // Rota bilgileri
                let routeInfoHTML = `
                    <div class="route-details">
                        <h6>Rota Bilgileri</h6>
                        <p>
                `;
                
                if (!isDriverView) {
                    routeInfoHTML += `<strong>Şoför:</strong> ${data.driver ? `${data.driver.user.first_name} ${data.driver.user.last_name}` : 'Atanmamış'}<br>`;
                }
                
                routeInfoHTML += `
                            <strong>Araç:</strong> ${data.vehicle ? data.vehicle.plate_number : 'Atanmamış'}<br>
                            <strong>Toplam Mesafe:</strong> ${data.total_distance?.toFixed(1)} km<br>
                            <strong>Toplam Desi:</strong> ${data.total_demand?.toFixed(2)}<br>
                            <strong>Durum:</strong> ${getStatusText(data.status)}
                        </p>
                    </div>
                `;
                
                // Sürücü görünümünde rota durumu güncelleme butonları ekle
                if (isDriverView) {
                    routeInfoHTML += `
                        <div class="mt-3">
                            <h6>Rota Durumu Güncelle</h6>
                            <div class="btn-group">
                                <button class="btn btn-sm status-btn btn-primary update-route-status" 
                                        data-route-id="${routeId}" 
                                        data-status="in_progress"
                                        ${data.status === 'in_progress' ? 'disabled' : ''}>
                                    <i class="bi bi-play-fill"></i> Başlat
                                </button>
                                <button class="btn btn-sm status-btn btn-success update-route-status" 
                                        data-route-id="${routeId}" 
                                        data-status="completed"
                                        ${data.status === 'completed' ? 'disabled' : ''}>
                                    <i class="bi bi-check-lg"></i> Tamamlandı
                                </button>
                                <button class="btn btn-sm status-btn btn-warning update-route-status" 
                                        data-route-id="${routeId}" 
                                        data-status="cancelled"
                                        ${data.status === 'cancelled' ? 'disabled' : ''}>
                                    <i class="bi bi-x-lg"></i> İptal Et
                                </button>
                            </div>
                        </div>
                    `;
                }
                
                document.getElementById(infoId).innerHTML = routeInfoHTML;
                
                // Rota durumu güncelleme butonlarına olay dinleyicileri ekle
                if (isDriverView) {
                    document.querySelectorAll('.update-route-status').forEach(button => {
                        button.addEventListener('click', function() {
                            updateRouteStatus(
                                this.dataset.routeId,
                                this.dataset.status
                            );
                        });
                    });
                }
                
                // Duraklar listesi (sadece sürücü görünümünde)
                if (isDriverView && stopsId && document.getElementById(stopsId)) {
                    // Durak listesi başlığı
                    let stopsHTML = `<div class="mt-4"><h6>Duraklar</h6>`;
                    
                    // Durakları listele
                    stopsHTML += data.stops.map((stop, index) => `
                        <div class="route-stop mb-3 p-2">
                            <div class="d-flex justify-content-between align-items-center">
                                <div>
                                    <strong>${index + 1}. ${stop.customer.name}</strong>
                                    <div><small>${stop.customer.address}</small></div>
                                    <div><small>İletişim: ${stop.customer.contact_person} - ${stop.customer.contact_phone}</small></div>
                                    ${stop.notes ? `<div class="mt-1 text-info"><small><i class="bi bi-journal-text"></i> Not: ${stop.notes}</small></div>` : ''}
                                </div>
                                <div class="d-flex align-items-center">
                                    <button class="btn btn-sm btn-outline-info note-btn add-note-btn" 
                                            data-route-id="${routeId}" 
                                            data-stop-id="${stop.id}"
                                            title="Not Ekle">
                                        <i class="bi bi-journal-plus"></i>
                                    </button>
                                    <span class="badge status-badge bg-${getStatusBadgeColor(stop.status)}">${getStatusText(stop.status)}</span>
                                </div>
                            </div>
                            <div class="mt-2">
                                <div class="btn-group" role="group">
                                    <button class="btn btn-sm status-btn ${stop.status === 'completed' ? 'btn-success' : 'btn-outline-success'} update-stop-status" 
                                            data-route-id="${routeId}" 
                                            data-stop-id="${stop.id}" 
                                            data-status="completed"
                                            ${stop.status === 'completed' || data.status !== 'in_progress' ? 'disabled' : ''}>
                                        <i class="bi bi-check-lg"></i> Tamamlandı
                                    </button>
                                    <button class="btn btn-sm status-btn ${stop.status === 'failed' ? 'btn-danger' : 'btn-outline-danger'} update-stop-status" 
                                            data-route-id="${routeId}" 
                                            data-stop-id="${stop.id}" 
                                            data-status="failed"
                                            ${stop.status === 'failed' || data.status !== 'in_progress' ? 'disabled' : ''}>
                                        <i class="bi bi-x-lg"></i> Başarısız
                                    </button>
                                </div>
                            </div>
                        </div>
                    `).join('');
                    
                    stopsHTML += `</div>`;
                    
                    document.getElementById(stopsId).innerHTML = stopsHTML;
                    
                    // Durak durumu güncelleme butonlarına olay dinleyicileri ekle
                    document.querySelectorAll('.update-stop-status').forEach(button => {
                        button.addEventListener('click', function() {
                            updateStopStatus(
                                this.dataset.routeId,
                                this.dataset.stopId,
                                this.dataset.status
                            );
                        });
                    });
                    
                    // Not ekleme butonlarına olay dinleyicileri ekle
                    document.querySelectorAll('.add-note-btn').forEach(button => {
                        button.addEventListener('click', function() {
                            addStopNote(
                                this.dataset.routeId,
                                this.dataset.stopId
                            );
                        });
                    });
                }
            })
            .catch(error => {
                console.error('Rota detayları alınırken hata:', error);
                if (document.getElementById(infoId)) {
                    document.getElementById(infoId).innerHTML = `
                        <div class="alert alert-danger">
                            Rota detayları yüklenirken bir hata oluştu: ${error.message}
                        </div>
                    `;
                }
                if (stopsId && document.getElementById(stopsId)) {
                    document.getElementById(stopsId).innerHTML = '';
                }
            });
    });
    
    // Modal kapatıldığında haritayı temizle
    document.getElementById(modalId).addEventListener('hidden.bs.modal', function () {
        if (routeMap) {
            routeMap.remove();
            routeMap = null;
        }
        routeMarkers = [];
        routePolylines = [];
    });
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

/**
 * OSRM API kullanarak iki nokta arasındaki rota çizgisini çizer
 * Bu fonksiyon artık kullanılmıyor, daha hızlı yükleme için basit çizgiler kullanıyoruz
 * @param {Array} start - Başlangıç noktası [lat, lng]
 * @param {Array} end - Bitiş noktası [lat, lng]
 * @param {string} color - Çizgi rengi
 * @returns {Promise} - Mesafe ve süre bilgisi
 */
async function drawRouteLine(start, end, color) {
    try {
        const response = await fetch(
            `https://router.project-osrm.org/route/v1/driving/${start[1]},${start[0]};${end[1]},${end[0]}?overview=full&geometries=geojson`
        );
        const data = await response.json();
        
        if (data.code !== 'Ok' || !data.routes || !data.routes[0]) {
            throw new Error('Rota alınamadı');
        }
        
        const polyline = L.polyline(
            data.routes[0].geometry.coordinates.map(coord => [coord[1], coord[0]]),
            {
                color: color,
                weight: 3,
                opacity: 0.8
            }
        );
        
        polyline.addTo(routeMap);
        routePolylines.push(polyline);
        
        return {
            distance: data.routes[0].distance / 1000,
            duration: Math.round(data.routes[0].duration / 60)
        };
    } catch (error) {
        console.error('Rota çizimi başarısız:', error);
        // Düz çizgi ile bağla
        const polyline = L.polyline([start, end], {
            color: color,
            weight: 3,
            opacity: 0.8,
            dashArray: '5, 10'
        });
        
        polyline.addTo(routeMap);
        routePolylines.push(polyline);
        
        return {
            distance: 0,
            duration: 0
        };
    }
} 