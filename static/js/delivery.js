/**
 * 校园外卖配送系统 - 前端交互逻辑
 * �� 阶段2升级：订单系统化（下单→列表→批次优化→配送模拟）
 */

let map, markerLayer, routeLayer, poiLayer, orderMarkerLayer;
let clickMarker = null;
let convergenceChart = null;
let currentBatchId = null;
let allPois = [];     // 缓存 POI 列表（下单下拉框用）

const COURIER_COLORS = [
    '#E74C3C', '#3498DB', '#27AE60', '#F39C12',
    '#9B59B6', '#1ABC9C', '#E67E22', '#C0392B'
];

const POI_CFG = {
    canteen:   { emoji: '🍽️', color: '#F39C12', border: '#D68910', size: 32, label: '食堂' },
    dormitory: { emoji: '🏠', color: '#3498DB', border: '#2471A3', size: 24, label: '宿舍' },
    teaching:  { emoji: '🏫', color: '#9B59B6', border: '#7D3C98', size: 24, label: '教学楼' },
    library:   { emoji: '📚', color: '#E67E22', border: '#CA6F1E', size: 24, label: '图书馆' },
    sports:    { emoji: '🏀', color: '#27AE60', border: '#1E8449', size: 24, label: '体育馆' },
    other:     { emoji: '📍', color: '#95A5A6', border: '#717D7E', size: 22, label: '其他' }
};

// ===== 初始化 =====
document.addEventListener('DOMContentLoaded', function () {
    map = L.map('map').setView([30.57978, 114.32819], 17);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap', maxZoom: 19
    }).addTo(map);

    markerLayer = L.layerGroup().addTo(map);
    routeLayer = L.layerGroup().addTo(map);
    poiLayer = L.layerGroup().addTo(map);
    orderMarkerLayer = L.layerGroup().addTo(map);  // ★ 新增：订单标记图层

    map.on('click', onMapClick);
    updateStatus('地图已加载 → 请先「📡 加载路网」', 'success');
});

function updateStatus(msg, type) {
    document.getElementById('statusPanel').innerHTML = `<p class="${type || ''}">${msg}</p>`;
}
function appendStatus(msg, type) {
    document.getElementById('statusPanel').innerHTML += `<p class="${type || ''}">${msg}</p>`;
}

// ===== 地图点击 =====
async function onMapClick(e) {
    try {
        const res = await fetch(`/delivery/nearest_node?lat=${e.latlng.lat}&lon=${e.latlng.lng}`);
        const r = await res.json();
        if (!r.success) return;
        const d = r.data;
        if (clickMarker) map.removeLayer(clickMarker);
        clickMarker = L.circleMarker([d.lat, d.lon], {
            radius: 10, fillColor: '#9B59B6', color: '#7D3C98', weight: 3, fillOpacity: 0.7
        }).addTo(map);
        clickMarker.bindPopup(
            `<b>最近节点</b><br>编号: <b>${d.node_index}</b><br>(${d.lat.toFixed(5)}, ${d.lon.toFixed(5)})<br>距: ${d.distance}米`
        ).openPopup();

        // 填入 POI 表单
        document.getElementById('poiNodeIndex').value = d.node_index;
        document.getElementById('poiLat').value = d.lat.toFixed(6);
        document.getElementById('poiLon').value = d.lon.toFixed(6);
        // ★ 也填入下单表单
        document.getElementById('orderNodeIndex').value = d.node_index;
    } catch (err) { console.error(err); }
}

// ================================================================
// POI 管理（阶段1，完全保留）
// ================================================================
async function initPOIs() {
    updateStatus('🔄 正在初始化校园地点...', 'loading');
    try {
        const res = await fetch('/delivery/pois/init', { method: 'POST' });
        const r = await res.json();
        if (r.success) {
            updateStatus(`✅ 初始化完成！共 ${r.data.total} 个地点`, 'success');
            renderPOIStats(r.data.pois); renderPOIList(r.data.pois); renderPOIOnMap(r.data.pois);
            cachePois(r.data.pois);
        } else { updateStatus(`❌ ${r.error}`, 'error'); }
    } catch (e) { updateStatus(`❌ ${e.message}`, 'error'); }
}

async function loadPOIs() {
    try {
        const res = await fetch('/delivery/pois');
        const r = await res.json();
        if (r.success) {
            renderPOIStats(r.data.pois); renderPOIList(r.data.pois); renderPOIOnMap(r.data.pois);
            cachePois(r.data.pois);
            appendStatus(`🗺️ 已刷新 ${r.data.total} 个地点`, 'success');
        }
    } catch (e) { console.error(e); }
}

/** ★ 新增：缓存 POI 并更新下单下拉框 */
function cachePois(pois) {
    allPois = pois;
    const sel = document.getElementById('orderDest');
    sel.innerHTML = '<option value="">-- 选择配送目的地 --</option>';
    pois.filter(p => p.poi_type !== 'canteen').forEach(p => {
        const cfg = POI_CFG[p.poi_type] || POI_CFG.other;
        sel.innerHTML += `<option value="${p.id}">${cfg.emoji} ${p.name} (#${p.node_index})</option>`;
    });
}

function renderPOIStats(pois) {
    const el = document.getElementById('poiStats'); el.style.display = 'flex';
    const c = {}; pois.forEach(p => { c[p.poi_type] = (c[p.poi_type] || 0) + 1; });
    el.innerHTML = Object.entries(c).map(([t, n]) => {
        const cfg = POI_CFG[t] || POI_CFG.other;
        return `<span class="tag" style="background:${cfg.color}22;color:${cfg.border};">${cfg.emoji} ${cfg.label}: ${n}</span>`;
    }).join('');
}
function renderPOIList(pois) {
    const el = document.getElementById('poiList');
    if (!pois.length) { el.innerHTML = '<p style="font-size:12px;color:#888;">暂无地点</p>'; return; }
    el.innerHTML = pois.map(p => {
        const cfg = POI_CFG[p.poi_type] || POI_CFG.other;
        const del = p.poi_type !== 'canteen' ? `<button title="删除" onclick="deletePOI(${p.id},'${p.name}')">🗑️</button>` : '';
        return `<div class="poi-item ${p.poi_type}"><div><div class="poi-name">${cfg.emoji} ${p.name}</div><div class="poi-meta">#${p.node_index} | ${p.description || cfg.label}</div></div><div class="poi-actions"><button title="定位" onclick="locatePOI(${p.lat},${p.lon},'${p.name}')">📍</button>${del}</div></div>`;
    }).join('');
}
function renderPOIOnMap(pois) {
    poiLayer.clearLayers();
    pois.forEach(p => {
        if (!p.lat && !p.lon) return;
        const cfg = POI_CFG[p.poi_type] || POI_CFG.other;
        const icon = L.divIcon({ className: '', html: `<div style="width:${cfg.size}px;height:${cfg.size}px;background:${cfg.color};border:2px solid ${cfg.border};border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:${cfg.size*0.5}px;box-shadow:0 2px 6px rgba(0,0,0,0.3);">${cfg.emoji}</div>`, iconSize: [cfg.size, cfg.size], iconAnchor: [cfg.size/2, cfg.size/2] });
        L.marker([p.lat, p.lon], { icon }).bindPopup(`<b>${cfg.emoji} ${p.name}</b><br>${cfg.label} | #${p.node_index}<br>${p.description||''}`).addTo(poiLayer);
    });
}
function locatePOI(lat, lon, name) { map.setView([lat, lon], 18); L.popup().setLatLng([lat, lon]).setContent(`📍 ${name}`).openOn(map); }
async function createPOI() {
    const name = document.getElementById('poiName').value.trim();
    const type = document.getElementById('poiType').value;
    const desc = document.getElementById('poiDesc').value.trim();
    const idx = parseInt(document.getElementById('poiNodeIndex').value);
    if (!name) { alert('请输入名称！'); return; }
    if (!idx || idx < 1) { alert('请先在地图上点击选择位置！'); return; }
    try {
        const res = await fetch('/delivery/pois', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({name, poi_type: type, node_index: idx, description: desc, capacity: 0}) });
        const r = await res.json();
        if (r.success) { updateStatus(`✅ 已添加: ${name}`, 'success'); ['poiName','poiDesc','poiNodeIndex','poiLat','poiLon'].forEach(id => document.getElementById(id).value=''); loadPOIs(); }
        else { alert('失败: ' + r.error); }
    } catch (e) { alert(e.message); }
}
async function deletePOI(id, name) {
    if (!confirm(`删除「${name}」？`)) return;
    try { const res = await fetch(`/delivery/pois/${id}`, {method:'DELETE'}); const r = await res.json();
    if (r.success) { updateStatus(`✅ 已删除: ${name}`, 'success'); loadPOIs(); } else { alert(r.error); }
    } catch (e) { alert(e.message); }
}

// ================================================================
// ★ 阶段2核心：订单管理
// ================================================================

/** 手动下单 */
async function createOrder() {
    const poiId = document.getElementById('orderDest').value;
    const nodeIdx = parseInt(document.getElementById('orderNodeIndex').value);

    if (!poiId && (!nodeIdx || nodeIdx < 1)) {
        alert('请选择目的地，或在地图上点击选择位置！');
        return;
    }

    const body = {};
    if (poiId) { body.to_poi_id = parseInt(poiId); }
    else { body.to_node_index = nodeIdx; }

    try {
        const res = await fetch('/delivery/orders/create', {
            method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body)
        });
        const r = await res.json();
        if (r.success) {
            updateStatus(`✅ 下单成功！订单 #${r.data.id} → ${r.data.address}`, 'success');
            document.getElementById('orderDest').value = '';
            document.getElementById('orderNodeIndex').value = '';
            loadOrders();
        } else { alert('下单失败: ' + r.error); }
    } catch (e) { alert(e.message); }
}

/** 随机下单 */
async function randomOrders() {
    const n = parseInt(document.getElementById('numRandomOrders').value) || 10;
    updateStatus(`🔄 正在随机生成 ${n} 个订单...`, 'loading');
    try {
        const res = await fetch('/delivery/orders/random', {
            method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({num_orders: n})
        });
        const r = await res.json();
        if (r.success) {
            updateStatus(`✅ 已生成 ${r.data.count} 个订单并写入数据库`, 'success');
            loadOrders();
        } else { updateStatus(`❌ ${r.error}`, 'error'); }
    } catch (e) { updateStatus(`❌ ${e.message}`, 'error'); }
}

/** 加载订单列表 */
async function loadOrders() {
    const filter = document.getElementById('orderFilter').value;
    const url = filter ? `/delivery/orders?status=${filter}` : '/delivery/orders';
    try {
        const res = await fetch(url);
        const r = await res.json();
        if (!r.success) return;

        const { orders, pending_count } = r.data;

        // 更新 pending 徽标
        const badge = document.getElementById('pendingBadge');
        if (pending_count > 0) {
            badge.style.display = 'inline'; badge.textContent = pending_count;
        } else { badge.style.display = 'none'; }

        // 渲染列表
        const el = document.getElementById('orderList');
        if (!orders.length) { el.innerHTML = '<p style="font-size:12px;color:#888;">暂无订单</p>'; return; }

        el.innerHTML = orders.map(o => `
            <div class="order-item ${o.status}">
                <div class="order-info">
                    <span class="order-id">#${o.id}</span>
                    <span class="order-dest">${o.address}</span>
                </div>
                <span class="order-status ${o.status}">${o.status_label}</span>
            </div>
        `).join('');

        // 在地图上标注订单
        orderMarkerLayer.clearLayers();
        orders.forEach(o => {
            if (!o.lat || !o.lon) return;
            const color = o.status === 'pending' ? '#E74C3C' :
                          o.status === 'delivered' ? '#27AE60' : '#F39C12';
            L.circleMarker([o.lat, o.lon], {
                radius: 5, fillColor: color, color: '#fff', weight: 1.5, fillOpacity: 0.9
            }).bindPopup(`📦 #${o.id} ${o.address}<br>${o.status_label}`)
              .addTo(orderMarkerLayer);
        });
    } catch (e) { console.error(e); }
}

// ================================================================
// ★ 阶段2重写：批次优化
// ================================================================

async function runOptimize() {
    const btn = document.getElementById('btnOptimize');
    btn.disabled = true;
    updateStatus('🧬 正在优化 pending 订单...', 'loading');

    const params = {
        num_couriers: parseInt(document.getElementById('numCouriers').value),
        ga_params: {
            population_size: parseInt(document.getElementById('popSize').value),
            generations: parseInt(document.getElementById('generations').value),
            mutation_rate: parseFloat(document.getElementById('mutRate').value),
            crossover_rate: parseFloat(document.getElementById('crossRate').value),
            use_2opt: document.getElementById('use2opt').checked,
            apply_2opt_interval: 10
        }
    };

    try {
        const response = await fetch('/delivery/optimize', {
            method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(params)
        });
        const result = await response.json();

        if (result.success) {
            const d = result.data;
            currentBatchId = d.batch_id;

            routeLayer.clearLayers();
            L.circleMarker([d.canteen.lat, d.canteen.lon], {
                radius: 12, fillColor: '#F39C12', color: '#D68910', weight: 3, fillOpacity: 1
            }).bindPopup('🍽️ 嘉慧园食堂').addTo(routeLayer);

            const nc = params.num_couriers;
            for (let cid = 1; cid <= nc; cid++) {
                const detail = d.courier_details[cid];
                if (detail && detail.route_coords && detail.route_coords.length > 1) {
                    L.polyline(detail.route_coords, {
                        color: COURIER_COLORS[cid - 1], weight: 4, opacity: 0.8
                    }).bindPopup(`🚴 骑手 ${cid}<br>📦 ${detail.orders.length} 单<br>📏 ${detail.distance} 米`)
                      .addTo(routeLayer);
                }
            }

            updateStatus(
                `✅ 批次 #${d.batch_id} 优化完成！<br>` +
                `📦 ${d.order_count} 个订单 | 📏 ${d.optimal_distance} 米<br>` +
                `📊 平均每单: ${(d.optimal_distance / d.order_count).toFixed(2)} 米`,
                'success'
            );

            showCourierDetails(d.courier_details, nc);
            drawConvergenceChart(d.convergence);

            // 显示配送模拟面板
            document.getElementById('batchPanel').style.display = 'block';
            document.getElementById('currentBatchId').textContent = d.batch_id;

            // 刷新订单列表（状态已从 pending → accepted）
            loadOrders();
        } else {
            updateStatus(`❌ ${result.error}`, 'error');
        }
    } catch (e) {
        updateStatus(`❌ ${e.message}`, 'error');
    }
    btn.disabled = false;
}

/** 配送模拟：批量推进状态 */
async function batchAdvance(newStatus) {
    if (!currentBatchId) { alert('请先优化一个批次！'); return; }
    try {
        const res = await fetch('/delivery/orders/batch_status', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ batch_id: currentBatchId, status: newStatus })
        });
        const r = await res.json();
        if (r.success) {
            const labels = { picked_up: '已取餐', delivering: '配送中', delivered: '已送达' };
            updateStatus(`✅ 批次 #${currentBatchId}: ${r.data.updated} 个订单 → ${labels[newStatus]}`, 'success');
            loadOrders();
        } else { alert(r.error); }
    } catch (e) { alert(e.message); }
}

// ================================================================
// 路网加载 + 骑手详情 + 收敛曲线（保留）
// ================================================================

async function loadGraphInfo() {
    updateStatus('🔄 正在加载路网...', 'loading');
    try {
        const response = await fetch('/delivery/graph_info');
        const result = await response.json();
        if (result.success) {
            const d = result.data;
            updateStatus(
                `✅ 路网加载成功！<br>📍 ${d.school_name}<br>🔵 ${d.node_count} 节点 | ➖ ${d.edge_count} 边<br>👉 点击「🏗️ 初始化地点」`,
                'success'
            );
            map.setView([d.center_lat, d.center_lon], 17);
        } else { updateStatus(`❌ ${result.error}`, 'error'); }
    } catch (e) { updateStatus(`❌ ${e.message}`, 'error'); }
}

function showCourierDetails(details, numCouriers) {
    const panel = document.getElementById('courierPanel');
    const list = document.getElementById('courierList');
    panel.style.display = 'block'; list.innerHTML = '';
    for (let cid = 1; cid <= numCouriers; cid++) {
        const d = details[cid]; const c = COURIER_COLORS[cid - 1];
        const item = document.createElement('div');
        item.className = 'courier-item'; item.style.borderLeftColor = c;
        item.innerHTML = `<strong style="color:${c}">骑手 ${cid}</strong><br>📦 ${d.orders.length} 单 | 📏 ${d.distance} 米`;
        list.appendChild(item);
    }
}

function drawConvergenceChart(convergence) {
    const container = document.getElementById('chartContainer');
    container.style.display = 'block';
    const ctx = document.getElementById('convergenceChart').getContext('2d');
    if (convergenceChart) convergenceChart.destroy();
    convergenceChart = new Chart(ctx, {
        type: 'line',
        data: { labels: convergence.map((_, i) => i + 1), datasets: [{ label: '最优距离 (米)', data: convergence, borderColor: '#E74C3C', backgroundColor: 'rgba(231,76,60,0.1)', fill: true, tension: 0.1, pointRadius: 0 }] },
        options: { responsive: true, plugins: { title: { display: true, text: 'GA + 2-opt 收敛过程' } }, scales: { x: { title: { display: true, text: '代数' } }, y: { title: { display: true, text: '距离 (米)' } } } }
    });
}