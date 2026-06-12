# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID


def post_init(cr, registry):
    """Post-install hook: ensure there is an `avicola.veterinario` record
    for each user that already belongs to the `gestion_avicola.group_veterinario` group.
    This helps when installing into an existing database where the group
    membership is preconfigured.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        group = env.ref('gestion_avicola.group_veterinario')
    except Exception:
        group = None
    if not group:
        return
    users = env['res.users'].search([('groups_id', 'in', group.id)])
    for user in users:
        vet = env['avicola.veterinario'].search([('user_id', '=', user.id)], limit=1)
        if not vet:
            env['avicola.veterinario'].create({
                'user_id': user.id,
                'name': user.name or user.login,
            })
