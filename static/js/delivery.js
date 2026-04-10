/**
 * 校园外卖配送系统 - 前端交互逻辑
 * ★ 阶段1升级：新增 POI 图层 + 地图点击 + 地点管理
 */

// ===== 全局变量 =====
let map;
let orderData = null;
let markerLayer, routeLayer, poiLayer;  // ★ 新增 poiLayer
let clickMarker = null;                  // ★ 新增：点击临时标记
let convergenceChart = null;

const COURIER_COLORS = [
    '#E74C3C', '#3498DB', '#27AE60', '#F39C12',
    '#9B59B6', '#1ABC9C', '#E67E22', '#C0392B'
];

// ★ 新增：POI 类型 → 图标/颜色/大小 映射
const POI_CFG = {
    canteen:   { emoji: '🍽️', color: '#F39C12', border: '#D68910', size: 32, label: '食堂' },
    dormitory: { emoji: '🏠', color: '#3498DB', border: '#2471A3', size: 24, label: '宿舍' },
    teaching:  { emoji: '🏫', color: '#9B59B6', border: '#7D3C98', size: 24, label: '教学楼' },
    library:   { emoji: '📚', color: '#E67E22', border: '#CA6F1E', size: 24, label: '图书馆' },
    sports:    { emoji: '🏀', color: '#27AE60', border: '#1E8449', size: 24, label: '体育馆' },
    other:     { emoji: '📍', color: '#95A5A6', border: '#717D7E', size: 22, label: '其他' }
};


// ===== 页面加载时初始化 =====
document.addEventListener('DOMContentLoaded', function () {
    map = L.map('map').setView([30.57978, 114.32819], 17);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap', maxZoom: 19
    }).addTo(map);

    markerLayer = L.layerGroup().addTo(map);
    routeLayer  = L.layerGroup().addTo(map);
    poiLayer    = L.layerGroup().addTo(map);  // ★ 新增

    // ★ 新增：地图点击 → 查最近节点
    map.on('click', onMapClick);

    updateStatus('地图已加载 → 请先「📡 加载路网」', 'success');
});


// ===== 工具函数 =====
function updateStatus(msg, type) {
    document.getElementById('statusPanel').innerHTML = `<p class="${type||''}">${msg}</p>`;
}
function appendStatus(msg, type) {
    document.getElementById('statusPanel').innerHTML += `<p class="${type||''}">${msg}</p>`;
}


// ================================================================
// ★ 阶段1核心：地图点击 → 查找最近路网节点
// ================================================================
async function onMapClick(e) {
    try {
        const res = await fetch(`/delivery/nearest_node?lat=${e.latlng.lat}&lon=${e.latlng.lng}`);
        const r = await res.json();
        if (!r.success) return;

        const d = r.data;
        if (clickMarker) map.removeLayer(clickMarker);

        clickMarker = L.circleMarker([d.lat, d.lon], {
            radius: 10, fillColor: '#9B59B6', color: '#7D3C98',
            weight: 3, fillOpacity: 0.7
        }).addTo(map);

        clickMarker.bindPopup(
            `<b>最近路网节点</b><br>` +
            `编号: <b>${d.node_index}</b><br>` +
            `坐标: (${d.lat.toFixed(5)}, ${d.lon.toFixed(5)})<br>` +
            `距点击: ${d.distance}米`
        ).openPopup();

        // 自动填入添加表单
        document.getElementById('poiNodeIndex').value = d.node_index;
        document.getElementById('poiLat').value = d.lat.toFixed(6);
        document.getElementById('poiLon').value = d.lon.toFixed(6);
    } catch (err) {
        console.error('查询最近节点失败:', err);
    }
}


// ================================================================
// ★ 阶段1核心：POI 管理
// ================================================================

/** 初始化 POI（从 config.py 预设写入数据库） */
async function initPOIs() {
    updateStatus('🔄 正在初始化校园地点...', 'loading');
    try {
        const res = await fetch('/delivery/pois/init', { method: 'POST' });
        const r = await res.json();
        if (r.success) {
            updateStatus(`✅ 初始化完成！新增 ${r.data.added} 个，共 ${r.data.total} 个地点`, 'success');
            renderPOIStats(r.data.pois);
            renderPOIList(r.data.pois);
            renderPOIOnMap(r.data.pois);
        } else {
            updateStatus(`❌ ${r.error}`, 'error');
        }
    } catch (e) { updateStatus(`❌ 网络错误: ${e.message}`, 'error'); }
}

/** 加载/刷新 POI */
async function loadPOIs() {
    try {
        const res = await fetch('/delivery/pois');
        const r = await res.json();
        if (r.success) {
            renderPOIStats(r.data.pois);
            renderPOIList(r.data.pois);
            renderPOIOnMap(r.data.pois);
            appendStatus(`🗺️ 已刷新 ${r.data.total} 个地点`, 'success');
        }
    } catch (e) { console.error(e); }
}

/** 渲染 POI 统计徽标 */
function renderPOIStats(pois) {
    const el = document.getElementById('poiStats');
    el.style.display = 'flex';
    const counts = {};
    pois.forEach(p => { counts[p.poi_type] = (counts[p.poi_type] || 0) + 1; });
    el.innerHTML = Object.entries(counts).map(([type, n]) => {
        const cfg = POI_CFG[type] || POI_CFG.other;
        return `<span class="tag" style="background:${cfg.color}22;color:${cfg.border};">${cfg.emoji} ${cfg.label}: ${n}</span>`;
    }).join('');
}

/** 渲染左侧 POI 列表 */
function renderPOIList(pois) {
    const el = document.getElementById('poiList');
    if (!pois.length) { el.innerHTML = '<p style="font-size:12px;color:#888;">暂无地点</p>'; return; }
    el.innerHTML = pois.map(p => {
        const cfg = POI_CFG[p.poi_type] || POI_CFG.other;
        const canDel = p.poi_type !== 'canteen';
        return `<div class="poi-item ${p.poi_type}">
            <div>
                <div class="poi-name">${cfg.emoji} ${p.name}</div>
                <div class="poi-meta">#${p.node_index} | ${p.description || cfg.label}</div>
            </div>
            <div class="poi-actions">
                <button title="定位" onclick="locatePOI(${p.lat},${p.lon},'${p.name}')">📍</button>
                ${canDel ? `<button title="删除" onclick="deletePOI(${p.id},'${p.name}')">🗑️</button>` : ''}
            </div>
        </div>`;
    }).join('');
}

/** 在地图上渲染 POI 图标 */
function renderPOIOnMap(pois) {
    poiLayer.clearLayers();
    pois.forEach(p => {
        if (!p.lat && !p.lon) return;
        const cfg = POI_CFG[p.poi_type] || POI_CFG.other;
        const icon = L.divIcon({
            className: '',
            html: `<div style="
                width:${cfg.size}px; height:${cfg.size}px;
                background:${cfg.color}; border:2px solid ${cfg.border};
                border-radius:50%; display:flex; align-items:center; justify-content:center;
                font-size:${cfg.size * 0.5}px; box-shadow:0 2px 6px rgba(0,0,0,0.3);
            ">${cfg.emoji}</div>`,
            iconSize: [cfg.size, cfg.size],
            iconAnchor: [cfg.size / 2, cfg.size / 2]
        });
        L.marker([p.lat, p.lon], { icon })
            .bindPopup(`<b>${cfg.emoji} ${p.name}</b><br>类型: ${cfg.label}<br>节点: #${p.node_index}<br>${p.description || ''}`)
            .addTo(poiLayer);
    });
}

/** 定位到某个 POI */
function locatePOI(lat, lon, name) {
    map.setView([lat, lon], 18);
    L.popup().setLatLng([lat, lon]).setContent(`📍 ${name}`).openOn(map);
}

/** 创建新 POI */
async function createPOI() {
    const name = document.getElementById('poiName').value.trim();
    const poiType = document.getElementById('poiType').value;
    const desc = document.getElementById('poiDesc').value.trim();
    const idx = parseInt(document.getElementById('poiNodeIndex').value);

    if (!name) { alert('请输入名称！'); return; }
    if (!idx || idx < 1) { alert('请先在地图上点击选择位置！'); return; }

    try {
        const res = await fetch('/delivery/pois', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, poi_type: poiType, node_index: idx, description: desc, capacity: 0 })
        });
        const r = await res.json();
        if (r.success) {
            updateStatus(`✅ 已添加: ${name}`, 'success');
            // 清空表单
            document.getElementById('poiName').value = '';
            document.getElementById('poiDesc').value = '';
            document.getElementById('poiNodeIndex').value = '';
            document.getElementById('poiLat').value = '';
            document.getElementById('poiLon').value = '';
            loadPOIs();
        } else { alert('添加失败: ' + r.error); }
    } catch (e) { alert('网络错误: ' + e.message); }
}

/** 删除 POI */
async function deletePOI(id, name) {
    if (!confirm(`确定删除「${name}���吗？`)) return;
    try {
        const res = await fetch(`/delivery/pois/${id}`, { method: 'DELETE' });
        const r = await res.json();
        if (r.success) { updateStatus(`✅ 已删除: ${name}`, 'success'); loadPOIs(); }
        else { alert('删除失败: ' + r.error); }
    } catch (e) { alert('网络错误: ' + e.message); }
}


// ================================================================
// 原有功能（完全不变）
// ================================================================

async function loadGraphInfo() {
    updateStatus('🔄 正在加载路网数据（首次可能较慢）...', 'loading');
    try {
        const response = await fetch('/delivery/graph_info');
        const result = await response.json();
        if (result.success) {
            const d = result.data;
            updateStatus(
                `✅ 路网加载成功！<br>` +
                `📍 ${d.school_name}<br>` +
                `🔵 节点: ${d.node_count} 个 | ➖ 边: ${d.edge_count} 条<br>` +
                `📏 半径: ${d.radius} 米<br>` +
                `👉 现在点击「🏗️ 初始化地点」`,
                'success'
            );
            map.setView([d.center_lat, d.center_lon], 17);
        } else {
            updateStatus(`❌ 加载失败: ${result.error}`, 'error');
        }
    } catch (e) {
        updateStatus(`❌ 网络错误: ${e.message}`, 'error');
    }
}

async function generateOrders() {
    const numOrders = parseInt(document.getElementById('numOrders').value);
    updateStatus('🔄 正在生成订单...', 'loading');
    try {
        const response = await fetch('/delivery/generate_orders', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ num_orders: numOrders })
        });
        const result = await response.json();
        if (result.success) {
            orderData = result.data;
            markerLayer.clearLayers();
            routeLayer.clearLayers();
            orderData.orders.forEach(order => {
                L.circleMarker([order.lat, order.lon], {
                    radius: 6, fillColor: '#E74C3C', color: '#C0392B',
                    weight: 2, fillOpacity: 0.8
                }).bindPopup(`📦 订单 ${order.order_id}<br>节点: #${order.node_id}`)
                  .addTo(markerLayer);
            });
            updateStatus(
                `✅ 已生成 ${numOrders} 个订单（红色圆点）<br>👉 点击「🚀 开始优化」`,
                'success'
            );
        } else {
            updateStatus(`❌ 生成失败: ${result.error}`, 'error');
        }
    } catch (e) {
        updateStatus(`❌ 网络错误: ${e.message}`, 'error');
    }
}

async function runOptimize() {
    if (!orderData) { updateStatus('⚠️ 请先生成订单！', 'error'); return; }
    const btn = document.getElementById('btnOptimize');
    btn.disabled = true;
    updateStatus('🧬 正在运行 GA+2-opt 优化...', 'loading');

    const params = {
        order_nodes: orderData.order_nodes,
        order_ids: orderData.order_ids,
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
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params)
        });
        const result = await response.json();
        if (result.success) {
            const d = result.data;
            routeLayer.clearLayers();
            L.circleMarker([d.canteen.lat, d.canteen.lon], {
                radius: 12, fillColor: '#F39C12', color: '#D68910',
                weight: 3, fillOpacity: 1
            }).bindPopup('🍽️ 嘉慧园食堂（起点）').addTo(routeLayer);

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
                `✅ 优化完成！<br>📏 总距离: ${d.optimal_distance} 米<br>📊 平均每单: ${(d.optimal_distance / orderData.orders.length).toFixed(2)} 米`,
                'success'
            );
            showCourierDetails(d.courier_details, nc);
            drawConvergenceChart(d.convergence);
        } else {
            updateStatus(`❌ 优化失败: ${result.error}`, 'error');
        }
    } catch (e) {
        updateStatus(`❌ 网络错误: ${e.message}`, 'error');
    }
    btn.disabled = false;
}

function showCourierDetails(details, numCouriers) {
    const panel = document.getElementById('courierPanel');
    const list = document.getElementById('courierList');
    panel.style.display = 'block';
    list.innerHTML = '';
    for (let cid = 1; cid <= numCouriers; cid++) {
        const d = details[cid];
        const c = COURIER_COLORS[cid - 1];
        const item = document.createElement('div');
        item.className = 'courier-item';
        item.style.borderLeftColor = c;
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
        data: {
            labels: convergence.map((_, i) => i + 1),
            datasets: [{
                label: '最优距离 (米)', data: convergence,
                borderColor: '#E74C3C', backgroundColor: 'rgba(231,76,60,0.1)',
                fill: true, tension: 0.1, pointRadius: 0
            }]
        },
        options: {
            responsive: true,
            plugins: { title: { display: true, text: 'GA + 2-opt 收敛过程' } },
            scales: {
                x: { title: { display: true, text: '代数' } },
                y: { title: { display: true, text: '距离 (米)' } }
            }
        }
    });
}