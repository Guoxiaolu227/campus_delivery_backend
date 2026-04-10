/**
 * 校园外卖配送系统 - 前端交互逻辑
 *
 * 工作流程：
 * 1. 页面加载 → 初始化 Leaflet 地图
 * 2. 点击"加载路网" → 调用 /delivery/graph_info → 显示基本信息
 * 3. 点击"生成订单" → 调用 /delivery/generate_orders → 在地图上标注订单点
 * 4. 点击"开始优化" → 调用 /delivery/optimize → 绘制最优路线 + 收敛曲线
 */

// ===== 全局变量 =====
let map;                    // Leaflet 地图对象
let orderData = null;       // 当前生成的订单数据
let markerLayer;            // 地图标记图层
let routeLayer;             // 地图路线图层
let convergenceChart = null; // Chart.js 图表对象

// 骑手颜色列表（最多支持8个骑手）
const COURIER_COLORS = [
    '#E74C3C', '#3498DB', '#27AE60', '#F39C12',
    '#9B59B6', '#1ABC9C', '#E67E22', '#C0392B'
];


// ===== 页面加载时初始化地图 =====
document.addEventListener('DOMContentLoaded', function () {
    // 创建 Leaflet 地图，中心设为武汉理工大学
    map = L.map('map').setView([30.57978, 114.32819], 17);

    // 添加 OpenStreetMap 瓦片图层
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 19
    }).addTo(map);

    // 初始化图层组（方便后续清除重绘）
    markerLayer = L.layerGroup().addTo(map);
    routeLayer = L.layerGroup().addTo(map);

    updateStatus('地图加载完成，请点击「加载路网」开始', 'success');
});


// ===== 工具函数：更新状态面板 =====
function updateStatus(message, type) {
    const panel = document.getElementById('statusPanel');
    panel.innerHTML = `<p class="${type || ''}">${message}</p>`;
}

function appendStatus(message, type) {
    const panel = document.getElementById('statusPanel');
    panel.innerHTML += `<p class="${type || ''}">${message}</p>`;
}


// ===== 功能1：加载路网信息 =====
async function loadGraphInfo() {
    const btn = document.getElementById('btnLoadGraph');
    btn.disabled = true;
    updateStatus('🔄 正在加载路网数据（首次加载需要下载地图，可能较慢）...', 'loading');

    try {
        const response = await fetch('/delivery/graph_info');
        const result = await response.json();

        if (result.success) {
            const d = result.data;
            updateStatus(
                `✅ 路网加载成功！<br>` +
                `📍 学校: ${d.school_name}<br>` +
                `🔵 节点: ${d.node_count} 个<br>` +
                `➖ 边: ${d.edge_count} 条<br>` +
                `📏 半径: ${d.radius} 米`,
                'success'
            );

            // 将地图中心移到学校位置
            map.setView([d.center_lat, d.center_lon], 17);
        } else {
            updateStatus(`❌ 加载失败: ${result.error}`, 'error');
        }
    } catch (e) {
        updateStatus(`❌ 网络错误: ${e.message}`, 'error');
    }

    btn.disabled = false;
}


// ===== 功能2：生成随机订单 =====
async function generateOrders() {
    const btn = document.getElementById('btnGenOrders');
    btn.disabled = true;
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

            // 清除旧标记
            markerLayer.clearLayers();
            routeLayer.clearLayers();

            // 在地图上标注每个订单点
            orderData.orders.forEach(order => {
                const marker = L.circleMarker([order.lat, order.lon], {
                    radius: 6,
                    fillColor: '#3498DB',
                    color: '#2471A3',
                    weight: 2,
                    fillOpacity: 0.8
                }).bindPopup(`订单 ${order.order_id}<br>节点编号: ${order.node_id}`);

                markerLayer.addLayer(marker);
            });

            updateStatus(
                `✅ 已生成 ${numOrders} 个订单<br>` +
                `📍 订单点已标注在地图上（蓝色圆点）<br>` +
                `👉 现在可以点击「开始优化」`,
                'success'
            );
        } else {
            updateStatus(`❌ 生成失败: ${result.error}`, 'error');
        }
    } catch (e) {
        updateStatus(`❌ 网络错误: ${e.message}`, 'error');
    }

    btn.disabled = false;
}


// ===== 功能3：运行 GA+2-opt 优化 =====
async function runOptimize() {
    if (!orderData) {
        updateStatus('⚠️ 请先生成订单！', 'error');
        return;
    }

    const btn = document.getElementById('btnOptimize');
    btn.disabled = true;

    updateStatus('🧬 正在运行 GA+2-opt 优化（请耐心等待）...', 'loading');

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

            // 清除旧路线
            routeLayer.clearLayers();

            // 标记食堂（黄色大圆点）
            L.circleMarker([d.canteen.lat, d.canteen.lon], {
                radius: 12,
                fillColor: '#F39C12',
                color: '#D68910',
                weight: 3,
                fillOpacity: 1
            }).bindPopup('🍽️ 食堂（起点）').addTo(routeLayer);

            // 绘制每个骑手的路线（不同颜色）
            const numCouriers = params.num_couriers;
            for (let cid = 1; cid <= numCouriers; cid++) {
                const detail = d.courier_details[cid];
                if (detail && detail.route_coords && detail.route_coords.length > 1) {
                    L.polyline(detail.route_coords, {
                        color: COURIER_COLORS[cid - 1],
                        weight: 4,
                        opacity: 0.8
                    }).bindPopup(
                        `骑手 ${cid}<br>` +
                        `订单数: ${detail.orders.length}<br>` +
                        `距离: ${detail.distance} 米`
                    ).addTo(routeLayer);
                }
            }

            // 更新状态
            updateStatus(
                `✅ 优化完成！<br>` +
                `📏 最优总距离: ${d.optimal_distance} 米<br>` +
                `📊 平均每单: ${(d.optimal_distance / orderData.orders.length).toFixed(2)} 米`,
                'success'
            );

            // 显示骑手分配结果
            showCourierDetails(d.courier_details, numCouriers);

            // 绘制收敛曲线
            drawConvergenceChart(d.convergence);

        } else {
            updateStatus(`❌ 优化失败: ${result.error}`, 'error');
        }
    } catch (e) {
        updateStatus(`❌ 网络错误: ${e.message}`, 'error');
    }

    btn.disabled = false;
}


// ===== 显示骑手分配详情 =====
function showCourierDetails(details, numCouriers) {
    const panel = document.getElementById('courierPanel');
    const list = document.getElementById('courierList');

    panel.style.display = 'block';
    list.innerHTML = '';

    for (let cid = 1; cid <= numCouriers; cid++) {
        const d = details[cid];
        const color = COURIER_COLORS[cid - 1];

        const item = document.createElement('div');
        item.className = 'courier-item';
        item.style.borderLeftColor = color;
        item.innerHTML = `
            <strong style="color:${color}">骑手 ${cid}</strong><br>
            📦 ${d.orders.length} 个订单 | 📏 ${d.distance} 米
        `;
        list.appendChild(item);
    }
}


// ===== 绘制收敛曲线（用 Chart.js 替代 matplotlib） =====
function drawConvergenceChart(convergence) {
    const container = document.getElementById('chartContainer');
    container.style.display = 'block';

    const ctx = document.getElementById('convergenceChart').getContext('2d');

    // 销毁旧图表
    if (convergenceChart) {
        convergenceChart.destroy();
    }

    convergenceChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: convergence.map((_, i) => i + 1),
            datasets: [{
                label: '最优距离 (米)',
                data: convergence,
                borderColor: '#E74C3C',
                backgroundColor: 'rgba(231, 76, 60, 0.1)',
                fill: true,
                tension: 0.1,
                pointRadius: 0
            }]
        },
        options: {
            responsive: true,
            plugins: {
                title: {
                    display: true,
                    text: 'GA + 2-opt 收敛过程'
                }
            },
            scales: {
                x: { title: { display: true, text: '代数' } },
                y: { title: { display: true, text: '距离 (米)' } }
            }
        }
    });
}