{
    'name': 'Gestión Avícola',
    'version': '18.0.1.0.0',
    'summary': 'Gestión de granjas, galpones, distribución y salidas avícolas',
    'author': 'Juan Arana',
    'category': 'Agriculture',
    'depends': ['base', 'web'],
    'assets': {
        'web.assets_backend': [
            'gestion_avicola/static/src/lib/chart.min.js',
            'gestion_avicola/static/src/css/dashboard.css',
            'gestion_avicola/static/src/js/dashboard.js',
        ],
    },
    'data': [
        'security/veterinario_security.xml',
        'security/ir.model.access.csv',
        'views/views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
