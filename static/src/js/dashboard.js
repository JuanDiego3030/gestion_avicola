odoo.define('gestion_avicola.dashboard', ['web.rpc', 'web.core'], function (rpc, core) {
    "use strict";

    console.log('gestion_avicola.dashboard: script loaded');
    console.log('gestion_avicola.dashboard: dependencies', !!rpc, !!core);

    function loadChartJs(callback) {
        if (window.Chart) { callback(); return; }
        var cdns = [
            'https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.min.js',
            'https://unpkg.com/chart.js@3.9.1/dist/chart.min.js'
        ];
        var attempt = 0;

        function tryLoad() {
            if (window.Chart) { callback(); return; }
            if (attempt >= cdns.length) {
                console.error('No se pudo cargar Chart.js desde los CDNs:', cdns);
                return;
            }
            var s = document.createElement('script');
            s.src = cdns[attempt];
            s.onload = function () { console.log('Chart.js cargado desde', cdns[attempt]); callback(); };
            s.onerror = function () {
                console.warn('Error cargando Chart.js desde', cdns[attempt]);
                attempt += 1;
                tryLoad();
            };
            document.head.appendChild(s);
        }

        tryLoad();
    }

    function renderCharts() {
        if (window.avicolaDashboardInlineLoaded || document.getElementById('avicola-granja-select')) {
            return;
        }
        console.log('gestion_avicola.dashboard: renderCharts start');

        var ctxA = document.getElementById('chart_galpones');
        if (!ctxA) {
            console.warn('Canvas chart_galpones no encontrado, reintentando...');
            setTimeout(renderCharts, 500);
            return;
        }

        rpc.query({
            model: 'avicola.galpon',
            method: 'search_read',
            args: [[], ['name', 'cantidad_actual', 'metros_cuadrados']],
        }).then(function (data) {
            console.log('gestion_avicola.dashboard: RPC data', data);
            var labels = data.map(function (d) { return d.name; });
            var counts = data.map(function (d) { return d.cantidad_actual || 0; });
            var densities = data.map(function (d) {
                return (d.metros_cuadrados && d.metros_cuadrados > 0)
                    ? (d.cantidad_actual / d.metros_cuadrados) : 0;
            });

            loadChartJs(function () {
                console.log('gestion_avicola.dashboard: Chart.js loaded',
                            typeof Chart !== 'undefined');
                try {
                    if (ctxA) {
                        new Chart(ctxA.getContext('2d'), {
                            type: 'bar',
                            data: {
                                labels: labels,
                                datasets: [{
                                    label: 'Aves por Galpón',
                                    data: counts,
                                    backgroundColor: '#722f77'
                                }]
                            },
                            options: { responsive: true, maintainAspectRatio: false }
                        });
                    }

                    var ctxB = document.getElementById('chart_densidades');
                    if (ctxB) {
                        new Chart(ctxB.getContext('2d'), {
                            type: 'line',
                            data: {
                                labels: labels,
                                datasets: [{
                                    label: 'Densidad (aves/m²)',
                                    data: densities,
                                    borderColor: '#e9b3f0',
                                    backgroundColor: 'rgba(233,179,240,0.15)',
                                    tension: 0.3
                                }]
                            },
                            options: { responsive: true, maintainAspectRatio: false }
                        });
                    }

                    var ctxC = document.getElementById('chart_pie');
                    if (ctxC) {
                        var palette = ['#5c2261', '#722f77', '#e9b3f0',
                                       '#dcb3e3', '#bca0bf'];
                        new Chart(ctxC.getContext('2d'), {
                            type: 'pie',
                            data: {
                                labels: labels,
                                datasets: [{
                                    data: counts,
                                    backgroundColor: labels.map(function (_, i) {
                                        return palette[i % palette.length];
                                    })
                                }]
                            },
                            options: { responsive: true, maintainAspectRatio: false }
                        });
                    }
                } catch (e) {
                    console.error('Error rendering charts', e);
                }
            });
        }).catch(function (err) {
            console.error('RPC error fetching galpones', err);
        });
    }

    // Escuchar el evento de Odoo cuando la vista está lista
    core.bus.on('DOM_updated', null, renderCharts);

    // Fallback con pequeño delay para la primera carga
    setTimeout(renderCharts, 400);
});