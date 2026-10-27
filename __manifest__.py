{
    'name': 'Gestión Avícola',
    'version': '19.0.1.0.0',
    'summary': 'Gestión de granjas, galpones, distribución y salidas avícolas',
    'author': 'Juan Arana',
    'category': 'Agriculture',
    'depends': ['base', 'web'],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'report/report_ticket_despacho.xml',
        'views/views.xml',
    ],
    'post_init_hook': 'post_init',
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
