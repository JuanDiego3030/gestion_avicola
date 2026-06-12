{
    'name': 'Gestión Avícola',
    'version': '18.0.1.0.0',
    'summary': 'Gestión de granjas, galpones, distribución y salidas avícolas',
    'author': 'Juan Arana',
    'category': 'Agriculture',
    'depends': ['base', 'web'],
    # Assets moved inline to XML to avoid bundling issues during development
    'assets': {},
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'views/views.xml',
    ],
    'post_init_hook': 'post_init',
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
