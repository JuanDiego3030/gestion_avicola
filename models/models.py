import logging

from odoo import api, fields, models
from odoo.exceptions import UserError


class AvicolaGranja(models.Model):
    _name = 'avicola.granja'
    _description = 'Granja de Engorde'

    name = fields.Char(string='Nombre', required=True)
    tipo = fields.Selection(
        [('propia', 'Propia'), ('alquilada', 'Alquilada')],
        string='Tipo', required=True, default='propia'
    )
    ubicacion = fields.Char(string='Ubicación')
    galpon_ids = fields.One2many('avicola.galpon', 'granja_id', string='Galpones')


class AvicolaGalpon(models.Model):
    _name = 'avicola.galpon'
    _description = 'Galpón'

    granja_id = fields.Many2one('avicola.granja', string='Granja',
                                required=True, ondelete='cascade')
    name = fields.Char(string='Nombre', required=True)
    metros_cuadrados = fields.Float(string='Metros Cuadrados', digits=(10, 2))
    capacidad_maxima = fields.Integer(string='Capacidad Máxima')
    cantidad_actual = fields.Integer(string='Cantidad Actual de Aves', default=0)
    densidad_actual = fields.Float(
        string='Densidad Actual (aves/m²)',
        compute='_compute_densidad_actual',
        store=True,
        digits=(10, 4),
    )
    mortalidad_ids = fields.One2many('avicola.mortalidad', 'galpon_id', string='Mortalidad')
    total_mortalidad = fields.Integer(
        string='Total Mortalidad',
        compute='_compute_total_mortalidad',
        store=True,
    )

    @api.depends('cantidad_actual', 'metros_cuadrados')
    def _compute_densidad_actual(self):
        for rec in self:
            if rec.metros_cuadrados and rec.metros_cuadrados > 0:
                rec.densidad_actual = rec.cantidad_actual / rec.metros_cuadrados
            else:
                rec.densidad_actual = 0.0

    @api.depends('mortalidad_ids.cantidad')
    def _compute_total_mortalidad(self):
        for rec in self:
            rec.total_mortalidad = sum(rec.mortalidad_ids.mapped('cantidad'))


class AvicolaDistribucion(models.Model):
    _name = 'avicola.distribucion'
    _description = 'Distribución de Pollitos'

    lote_incubadora = fields.Char(string='Lote Incubadora', required=True)
    fecha = fields.Date(string='Fecha', required=True, default=fields.Date.today)
    granja_id = fields.Many2one('avicola.granja', string='Granja', required=True)
    galpon_id = fields.Many2one(
        'avicola.galpon', string='Galpón', required=True,
        domain="[('granja_id', '=', granja_id)]"
    )
    cantidad = fields.Integer(string='Cantidad', required=True)
    estado = fields.Selection(
        [('borrador', 'Borrador'), ('confirmado', 'Confirmado')],
        string='Estado', default='borrador', required=True
    )

    def action_confirmar(self):
        for rec in self:
            if rec.estado == 'confirmado':
                raise UserError('Este registro ya está confirmado.')
            if not rec.galpon_id:
                raise UserError('Debe seleccionar un galpón.')
            rec.galpon_id.cantidad_actual += rec.cantidad
            rec.estado = 'confirmado'

    def action_borrador(self):
        for rec in self:
            if rec.estado == 'confirmado':
                rec.galpon_id.cantidad_actual -= rec.cantidad
            rec.estado = 'borrador'


class AvicolaMortalidad(models.Model):
    _name = 'avicola.mortalidad'
    _description = 'Registro de Mortalidad de Aves'

    lote_incubadora = fields.Char(string='Lote Incubadora', readonly=True)
    fecha = fields.Date(string='Fecha', required=True, default=fields.Date.today)
    granja_id = fields.Many2one('avicola.granja', string='Granja', required=True)
    galpon_id = fields.Many2one(
        'avicola.galpon', string='Galpón', required=True,
        domain="[('granja_id', '=', granja_id), ('cantidad_actual', '>', 0)]"
    )
    cantidad = fields.Integer(string='Cantidad Mortalidad', required=True)
    observaciones = fields.Text(string='Observaciones')
    estado = fields.Selection(
        [('borrador', 'Borrador'), ('confirmado', 'Confirmado')],
        string='Estado', default='borrador', required=True
    )

    @api.onchange('galpon_id')
    def _onchange_galpon_id(self):
        for rec in self:
            if rec.galpon_id:
                dist = self.env['avicola.distribucion'].search([
                    ('galpon_id', '=', rec.galpon_id.id),
                    ('estado', '=', 'confirmado')
                ], order='fecha desc', limit=1)
                rec.lote_incubadora = dist.lote_incubadora if dist else False
            else:
                rec.lote_incubadora = False

    def action_confirmar(self):
        for rec in self:
            if rec.estado == 'confirmado':
                raise UserError('Este registro ya está confirmado.')
            if not rec.galpon_id:
                raise UserError('Debe seleccionar un galpón.')
            if rec.galpon_id.cantidad_actual < rec.cantidad:
                raise UserError(
                    'No hay suficientes aves en el galpón para registrar esta mortalidad. '
                    f'Disponible: {rec.galpon_id.cantidad_actual}, solicitado: {rec.cantidad}'
                )
            rec.galpon_id.cantidad_actual -= rec.cantidad
            rec.estado = 'confirmado'

    def action_borrador(self):
        for rec in self:
            if rec.estado == 'confirmado':
                rec.galpon_id.cantidad_actual += rec.cantidad
            rec.estado = 'borrador'


class AvicolaSalida(models.Model):
    _name = 'avicola.salida'
    _description = 'Salida a Matadero'

    fecha = fields.Date(string='Fecha', required=True, default=fields.Date.today)
    granja_id = fields.Many2one('avicola.granja', string='Granja', required=True)
    galpon_id = fields.Many2one(
        'avicola.galpon', string='Galpón', required=True,
        domain="[('granja_id', '=', granja_id)]"
    )
    cantidad = fields.Integer(string='Cantidad', required=True)
    peso_total = fields.Float(string='Peso Total (kg)', digits=(10, 2))
    estado = fields.Selection(
        [('borrador', 'Borrador'), ('confirmado', 'Confirmado')],
        string='Estado', default='borrador', required=True
    )

    def action_confirmar(self):
        for rec in self:
            if rec.estado == 'confirmado':
                raise UserError('Este registro ya está confirmado.')
            if not rec.galpon_id:
                raise UserError('Debe seleccionar un galpón.')
            if rec.galpon_id.cantidad_actual < rec.cantidad:
                raise UserError(
                    f'No hay suficientes aves en el galpón. '
                    f'Disponible: {rec.galpon_id.cantidad_actual}, '
                    f'Solicitado: {rec.cantidad}'
                )
            rec.galpon_id.cantidad_actual -= rec.cantidad
            rec.estado = 'confirmado'

    def action_borrador(self):
        for rec in self:
            if rec.estado == 'confirmado':
                rec.galpon_id.cantidad_actual += rec.cantidad
            rec.estado = 'borrador'


class AvicolaDashboard(models.TransientModel):
    _name = 'avicola.dashboard'
    _description = 'Panel de Control Avícola'

    name = fields.Char(string="Dashboard", default="Panel de Control")

    selected_granja_id = fields.Many2one('avicola.granja', string='Granja seleccionada')
    mortalidad_percent = fields.Float(string='Mortalidad (%)', compute='_compute_mortalidad_percent')

    total_granjas = fields.Integer(string='Total Granjas', compute='_compute_metrics')
    total_galpones = fields.Integer(string='Total Galpones', compute='_compute_metrics')
    total_aves = fields.Integer(string='Población Total de Aves', compute='_compute_metrics')
    total_veterinarios = fields.Integer(string='Total Veterinarios', compute='_compute_metrics')
    total_ingresos_pollitos = fields.Integer(string='Pollitos Distribuidos',
                                             compute='_compute_metrics')
    total_salidas_matadero = fields.Integer(string='Aves Enviadas a Matadero',
                                            compute='_compute_metrics')
    peso_total_despachado = fields.Float(string='Peso Total Despachado (kg)',
                                         compute='_compute_metrics', digits=(10, 2))

    def _get_visible_granjas(self):
        veterinarian = self.env['avicola.veterinario'].search([
            ('user_id', '=', self.env.uid),
        ], limit=1)
        if veterinarian:
            return veterinarian.granja_ids
        return self.env['avicola.granja'].search([])

    @api.depends_context('dashboard_range')
    def _compute_metrics(self):
        Dist = self.env['avicola.distribucion']
        Salida = self.env['avicola.salida']

        for rec in self:
            visible_granjas = self._get_visible_granjas()
            rec.total_granjas = len(visible_granjas)

            galpones = self.env['avicola.galpon'].search([
                ('granja_id', 'in', visible_granjas.ids)
            ])
            rec.total_galpones = len(galpones)
            rec.total_aves = sum(galpones.mapped('cantidad_actual'))

            rec.total_ingresos_pollitos = sum(
                Dist.search([
                    ('estado', '=', 'confirmado'),
                    ('granja_id', 'in', visible_granjas.ids)
                ]).mapped('cantidad')
            )

            salidas_confirmadas = Salida.search([
                ('estado', '=', 'confirmado'),
                ('granja_id', 'in', visible_granjas.ids)
            ])
            rec.total_salidas_matadero = sum(salidas_confirmadas.mapped('cantidad'))
            rec.peso_total_despachado = sum(salidas_confirmadas.mapped('peso_total'))
            rec.total_veterinarios = self.env['avicola.veterinario'].search_count([])

    def action_refresh_metrics(self):
        self._compute_metrics()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_open_granjas(self):
        return {
            'name': 'Granjas',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.granja',
            'view_mode': 'list,form',
            'target': 'current',
        }

    def action_open_galpones(self):
        return {
            'name': 'Galpones',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.galpon',
            'view_mode': 'list,form',
            'target': 'current',
        }

    def action_open_distribuciones(self):
        return {
            'name': 'Distribuciones',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.distribucion',
            'view_mode': 'list,form',
            'target': 'current',
        }

    def action_open_salidas(self):
        return {
            'name': 'Salidas a Matadero',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.salida',
            'view_mode': 'list,form',
            'target': 'current',
        }

    def action_open_veterinarios(self):
        return {
            'name': 'Veterinarios',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.veterinario',
            'view_mode': 'list,form',
            'target': 'current',
        }

    def action_open_planificaciones(self):
        return {
            'name': 'Planificaciones de Vacunación',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.plan.vacunacion',
            'view_mode': 'list,form',
            'target': 'current',
        }

    @api.model
    def get_metrics(self):
        """Return dashboard metrics for the current user as a dict.

        Used by the dashboard JS to populate KPI cards via RPC.
        """
        Dist = self.env['avicola.distribucion']
        Salida = self.env['avicola.salida']

        # determine visible granjas for the current user
        veterinarian = self.env['avicola.veterinario'].search([
            ('user_id', '=', self.env.uid),
        ], limit=1)
        if veterinarian:
            visible_granjas = veterinarian.granja_ids
        else:
            visible_granjas = self.env['avicola.granja'].search([])

        galpones = self.env['avicola.galpon'].search([
            ('granja_id', 'in', visible_granjas.ids)
        ])

        total_granjas = len(visible_granjas)
        total_galpones = len(galpones)
        total_aves = sum(galpones.mapped('cantidad_actual'))

        total_ingresos_pollitos = sum(
            Dist.search([
                ('estado', '=', 'confirmado'),
                ('granja_id', 'in', visible_granjas.ids)
            ]).mapped('cantidad')
        )

        salidas_confirmadas = Salida.search([
            ('estado', '=', 'confirmado'),
            ('granja_id', 'in', visible_granjas.ids)
        ])
        total_salidas_matadero = sum(salidas_confirmadas.mapped('cantidad'))
        peso_total_despachado = sum(salidas_confirmadas.mapped('peso_total'))
        total_veterinarios = self.env['avicola.veterinario'].search_count([])

        return {
            'total_granjas': total_granjas,
            'total_galpones': total_galpones,
            'total_aves': total_aves,
            'total_veterinarios': total_veterinarios,
            'total_ingresos_pollitos': total_ingresos_pollitos,
            'total_salidas_matadero': total_salidas_matadero,
            'peso_total_despachado': float(peso_total_despachado) if peso_total_despachado else 0.0,
        }

    @api.model
    def get_available_granjas(self):
        veterinarian = self.env['avicola.veterinario'].search([
            ('user_id', '=', self.env.uid),
        ], limit=1)
        if veterinarian:
            granjas = veterinarian.granja_ids
        else:
            granjas = self.env['avicola.granja'].search([])
        return [{'id': granja.id, 'name': granja.name} for granja in granjas]

    @api.model
    def get_mortalidad_percentage(self, granja_id):
        """Return the mortality percentage for a given granja_id.

        Percentage is computed as: (total_mortalidad_confirmado / total_ingresos_confirmado) * 100
        If there are no confirmed ingresos, returns 0.0 to avoid division by zero.
        """
        if not granja_id:
            return 0.0
        Dist = self.env['avicola.distribucion']
        Mort = self.env['avicola.mortalidad']
        total_ingresos = sum(Dist.search([
            ('granja_id', '=', granja_id),
            ('estado', '=', 'confirmado')
        ]).mapped('cantidad'))
        total_mortalidad = sum(Mort.search([
            ('granja_id', '=', granja_id),
            ('estado', '=', 'confirmado')
        ]).mapped('cantidad'))
        if total_ingresos:
            return float(total_mortalidad) * 100.0 / float(total_ingresos)
        return 0.0


class AvicolaVeterinario(models.Model):
    _name = 'avicola.veterinario'
    _description = 'Veterinario'

    name = fields.Char(string='Nombre', required=True)
    user_id = fields.Many2one('res.users', string='Usuario', help='Usuario asociado al veterinario')
    granja_ids = fields.Many2many('avicola.granja', string='Granjas Asignadas')
    active = fields.Boolean(string='Activo', default=True)

    @api.onchange('user_id')
    def _onchange_user_id(self):
        for rec in self:
            if rec.user_id:
                rec.name = rec.user_id.name

    @api.model
    def create(self, vals):
        if vals.get('user_id'):
            existing = self.search([('user_id', '=', vals['user_id'])], limit=1)
            if existing:
                raise UserError('Este usuario ya está asignado a otro veterinario.')
            if not vals.get('name'):
                user = self.env['res.users'].browse(vals['user_id'])
                vals['name'] = user.name or False
        rec = super().create(vals)
        # ensure the linked user is in the veterinarian group
        try:
            vet_group = self.env.ref('gestion_avicola.group_veterinario')
        except Exception:
            vet_group = None
        if vet_group and rec.user_id:
            rec.user_id.sudo().write({'groups_id': [(4, vet_group.id)]})
        return rec

    def write(self, vals):
        res = super().write(vals)
        # if user_id changed or set, ensure the user is added to the veterinarian group
        try:
            vet_group = self.env.ref('gestion_avicola.group_veterinario')
        except Exception:
            vet_group = None
        if vet_group and 'user_id' in vals:
            for rec in self:
                if rec.user_id:
                    rec.user_id.sudo().write({'groups_id': [(4, vet_group.id)]})
        return res


class AvicolaPlanVacunacion(models.Model):
    _name = 'avicola.plan.vacunacion'
    _description = 'Planificación de Vacunación'

    name = fields.Char(string='Referencia', default='Plan de Vacunación', required=True)
    veterinario_id = fields.Many2one(
        'avicola.veterinario', string='Veterinario', required=True,
        default=lambda self: self._default_veterinario()
    )
    granja_id = fields.Many2one(
        'avicola.granja', string='Granja', required=True,
    )
    fecha_planificada = fields.Date(string='Fecha Planificada', required=True, default=fields.Date.today)
    descripcion = fields.Text(string='Descripción')
    user_is_veterinario = fields.Boolean(string='Usuario es veterinario', compute='_compute_user_is_veterinario')
    state = fields.Selection(
        [('borrador', 'Borrador'), ('programado', 'Programado'), ('realizado', 'Realizado')],
        string='Estado', default='borrador', required=True
    )

    @api.model
    def _default_veterinario(self):
        if self.env.uid:
            vet = self.env['avicola.veterinario'].search([('user_id', '=', self.env.uid)], limit=1)
            return vet.id if vet else False
        return False

    @api.depends()
    def _compute_user_is_veterinario(self):
        current_user = self.env.uid
        is_vet = bool(self.env['avicola.veterinario'].search([('user_id', '=', current_user)], limit=1))
        for rec in self:
            rec.user_is_veterinario = is_vet

    def fields_get(self, *args, **kwargs):
        # Delegate to super with whatever signature is used by the running Odoo
        res = super().fields_get(*args, **kwargs)
        try:
            vet = self.env['avicola.veterinario'].search([('user_id', '=', self.env.uid)], limit=1)
            if vet and isinstance(res, dict) and 'granja_id' in res:
                res['granja_id']['domain'] = [('id', 'in', vet.granja_ids.ids)]
            # also apply domain for the transient dashboard field used to select a granja
            if vet and isinstance(res, dict) and 'selected_granja_id' in res:
                res['selected_granja_id']['domain'] = [('id', 'in', vet.granja_ids.ids)]
        except Exception:
            pass
        return res

    @api.depends('selected_granja_id')
    def _compute_mortalidad_percent(self):
        for rec in self:
            if not rec.selected_granja_id:
                rec.mortalidad_percent = 0.0
                continue
            Dist = self.env['avicola.distribucion']
            Mort = self.env['avicola.mortalidad']
            total_ingresos = sum(Dist.search([
                ('granja_id', '=', rec.selected_granja_id.id),
                ('estado', '=', 'confirmado')
            ]).mapped('cantidad'))
            total_mortalidad = sum(Mort.search([
                ('granja_id', '=', rec.selected_granja_id.id),
                ('estado', '=', 'confirmado')
            ]).mapped('cantidad'))
            if total_ingresos:
                rec.mortalidad_percent = float(total_mortalidad) * 100.0 / float(total_ingresos)
            else:
                rec.mortalidad_percent = 0.0

    def action_open_mortalidad(self):
        self.ensure_one()
        domain = []
        if self.selected_granja_id:
            domain = [('granja_id', '=', self.selected_granja_id.id)]
        return {
            'name': 'Mortalidad de Aves',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.mortalidad',
            'view_mode': 'list,form',
            'target': 'current',
            'domain': domain,
        }

    @api.onchange('veterinario_id')
    def _onchange_veterinario_id(self):
        for rec in self:
            if rec.veterinario_id:
                allowed = rec.veterinario_id.granja_ids.ids
                if rec.granja_id and rec.granja_id.id not in allowed:
                    rec.granja_id = False
                return {'domain': {'granja_id': [('id', 'in', allowed)]}}
            else:
                # No veterinarian selected -> no available granjas
                rec.granja_id = False
                return {'domain': {'granja_id': []}}

    def action_programar(self):
        for rec in self:
            rec.state = 'programado'

    def action_realizar(self):
        for rec in self:
            rec.state = 'realizado'

    def write(self, vals):
        # Prevent a veterinarian user from changing the veterinario_id unless they are admin
        if 'veterinario_id' in vals and not self.env.user.has_group('base.group_system'):
            # check if current user is a veterinarian record
            vet = self.env['avicola.veterinario'].search([('user_id', '=', self.env.uid)], limit=1)
            if vet:
                # if trying to change to a different veterinarian, block
                for rec in self:
                    if rec.veterinario_id and vals.get('veterinario_id') and rec.veterinario_id.id != vals.get('veterinario_id'):
                        raise UserError('No tienes permiso para cambiar el Veterinario.')
        return super().write(vals)


class AvicolaDespacho(models.Model):
    _name = 'avicola.despacho'
    _description = 'Despacho de Aves Vivas'

    # Datos fijos (readonly, por si se quieren mostrar en el ticket)
    company_name = fields.Char(string='Empresa', default='DESPACHO AVES VIVAS\nAgrolucha, C.A.', readonly=True)
    company_rif = fields.Char(string='RIF', default='J-00089080-3', readonly=True)
    company_direccion = fields.Text(string='Dirección', default='Av. Las Delicias, Edf. Banvenez, piso Mzz 2 of. Mzz2, Urb. El Bosque Maracay Aragua.', readonly=True)

    # Datos variables
    fecha = fields.Datetime(string='Fecha', default=fields.Datetime.now)
    granja = fields.Many2one('avicola.granja', string='Granja')
    cliente = fields.Char(string='Cliente')
    placa = fields.Char(string='Placa')
    chofer = fields.Char(string='Chofer')
    cant_jaulas = fields.Integer(string='Cant. Jaulas')
    pollos_por_jaula = fields.Integer(string='Pollos/jaula')
    orden_compra = fields.Char(string='Orden de compra Nro')
    inicio_carga = fields.Datetime(string='Inicio de carga')
    final_carga = fields.Datetime(string='Final de carga')
    cuadrilla = fields.Char(string='Cuadrilla')
    cantidad_aves = fields.Integer(string='Cant. Aves')
    peso_neto = fields.Float(string='Peso Neto (kg)', digits=(12, 2))
    peso_promedio = fields.Float(string='Peso Promedio (kg)', compute='_compute_peso_promedio', store=True, digits=(10, 3))
    pollo_mojado = fields.Selection([( 'si','Si'),('no','No')], string='Pollo mojado')
    precinto_1 = fields.Char(string='Precinto 1')
    precinto_2 = fields.Char(string='Precinto 2')
    precinto = fields.Char(string='Precinto')
    supervisor = fields.Many2one('res.users', string='Supervisor')
    salida_id = fields.Many2one('avicola.salida', string='Salida relacionada', ondelete='cascade', readonly=True)

    @api.depends('peso_neto', 'cantidad_aves')
    def _compute_peso_promedio(self):
        for rec in self:
            if rec.cantidad_aves:
                rec.peso_promedio = float(rec.peso_neto or 0.0) / float(rec.cantidad_aves)
            else:
                rec.peso_promedio = 0.0

    def action_print_ticket(self):
        # Placeholder for printing action (to be implemented)
        return True

    @api.model
    def create(self, vals):
        rec = super(AvicolaDespacho, self).create(vals)
        try:
            salida_vals = {
                'fecha': rec.fecha,
                'granja_id': rec.granja.id if rec.granja else False,
                'cantidad': rec.cantidad_aves or 0,
                'peso_total': rec.peso_neto or 0.0,
                'estado': 'borrador'
            }
            salida = self.env['avicola.salida'].create(salida_vals)
            rec.salida_id = salida.id
        except Exception:
            # don't block despacho creation if salida cannot be created
            _logger = logging.getLogger(__name__)
            _logger.exception('No se pudo crear la salida relacionada para el despacho')
        return rec

    def write(self, vals):
        res = super(AvicolaDespacho, self).write(vals)
        for rec in self:
            if rec.salida_id:
                try:
                    update_vals = {}
                    if 'fecha' in vals:
                        update_vals['fecha'] = rec.fecha
                    if 'granja' in vals or 'granja_id' in vals:
                        update_vals['granja_id'] = rec.granja.id if rec.granja else False
                    if 'cantidad_aves' in vals:
                        update_vals['cantidad'] = rec.cantidad_aves or 0
                    if 'peso_neto' in vals:
                        update_vals['peso_total'] = rec.peso_neto or 0.0
                    if update_vals:
                        rec.salida_id.write(update_vals)
                except Exception:
                    logging.getLogger(__name__).exception('Error actualizando salida relacionada')
        return res

    def unlink(self):
        for rec in self:
            try:
                if rec.salida_id:
                    rec.salida_id.unlink()
            except Exception:
                logging.getLogger(__name__).exception('Error eliminando salida relacionada al borrar despacho')
        return super(AvicolaDespacho, self).unlink()

    def action_confirm_despacho(self):
        for rec in self:
            if not rec.salida_id:
                try:
                    salida_vals = {
                        'fecha': rec.fecha,
                        'granja_id': rec.granja.id if rec.granja else False,
                        'cantidad': rec.cantidad_aves or 0,
                        'peso_total': rec.peso_neto or 0.0,
                        'estado': 'confirmado'
                    }
                    salida = self.env['avicola.salida'].create(salida_vals)
                    rec.salida_id = salida.id
                except Exception:
                    logging.getLogger(__name__).exception('No se pudo crear la salida al confirmar despacho')
            else:
                try:
                    rec.salida_id.write({'estado': 'confirmado'})
                except Exception:
                    logging.getLogger(__name__).exception('No se pudo confirmar la salida relacionada')
        return True


class ResUsers(models.Model):
    _inherit = 'res.users'

    def write(self, vals):
        res = super().write(vals)
        # After write, if the user now has the 'gestion_avicola.group_veterinario' group,
        # ensure there is a corresponding avicola.veterinario record.
        try:
            vet_group = self.env.ref('gestion_avicola.group_veterinario')
        except Exception:
            vet_group = None
        if vet_group:
            for user in self:
                if vet_group in user.groups_id:
                    vet = self.env['avicola.veterinario'].search([('user_id', '=', user.id)], limit=1)
                    if not vet:
                        # create a veterinarian record linked to this user
                        self.env['avicola.veterinario'].create({
                            'user_id': user.id,
                            'name': user.name or user.login,
                        })
        return res
