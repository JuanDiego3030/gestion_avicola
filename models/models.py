# -*- coding: utf-8 -*-
import html
import logging
from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AvicolaGranja(models.Model):
    _name = 'avicola.granja'
    _description = 'Granja de Engorde'
    _order = 'name'

    name = fields.Char(string='Nombre', required=True)
    tipo = fields.Selection(
        [('propia', 'Propia'), ('alquilada', 'Alquilada')],
        string='Tipo', required=True, default='propia'
    )
    ubicacion = fields.Char(string='Ubicación')
    galpon_ids = fields.One2many('avicola.galpon', 'granja_id', string='Galpones')
    total_galpones = fields.Integer(string='Total Galpones', compute='_compute_totals', store=True)
    total_aves = fields.Integer(string='Población Total (Aves)', compute='_compute_totals', store=True)
    metros_totales = fields.Float(string='Superficie Total (m²)', compute='_compute_totals', store=True, digits=(10, 2))

    @api.depends('galpon_ids', 'galpon_ids.cantidad_actual', 'galpon_ids.metros_cuadrados')
    def _compute_totals(self):
        for rec in self:
            rec.total_galpones = len(rec.galpon_ids)
            rec.total_aves = sum(rec.galpon_ids.mapped('cantidad_actual'))
            rec.metros_totales = sum(rec.galpon_ids.mapped('metros_cuadrados'))


class AvicolaGalpon(models.Model):
    _name = 'avicola.galpon'
    _description = 'Galpón'
    _order = 'granja_id, name'

    granja_id = fields.Many2one('avicola.granja', string='Granja', required=True, ondelete='cascade')
    name = fields.Char(string='Nombre', required=True)
    metros_cuadrados = fields.Float(string='Metros Cuadrados', digits=(10, 2), default=0.0)
    capacidad_maxima = fields.Integer(string='Capacidad Máxima', default=0)
    cantidad_actual = fields.Integer(string='Cantidad Actual de Aves', default=0)
    densidad_actual = fields.Float(
        string='Densidad Actual (aves/m²)',
        compute='_compute_densidad_actual',
        store=True,
        digits=(10, 2),
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
    _order = 'fecha desc, id desc'

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
            if rec.cantidad <= 0:
                raise UserError('La cantidad de pollitos debe ser mayor a cero.')
            rec.galpon_id.cantidad_actual += rec.cantidad
            rec.estado = 'confirmado'

    def action_borrador(self):
        for rec in self:
            if rec.estado == 'confirmado':
                if rec.galpon_id.cantidad_actual < rec.cantidad:
                    raise UserError(
                        f'No se puede revertir: la cantidad actual en el galpón ({rec.galpon_id.cantidad_actual}) '
                        f'es menor que la cantidad distribuida ({rec.cantidad}).'
                    )
                rec.galpon_id.cantidad_actual -= rec.cantidad
            rec.estado = 'borrador'


class AvicolaMortalidad(models.Model):
    _name = 'avicola.mortalidad'
    _description = 'Registro de Mortalidad de Aves'
    _order = 'fecha desc, id desc'

    lote_incubadora = fields.Char(
        string='Lote Incubadora',
        compute='_compute_lote_incubadora',
        store=True,
        readonly=False,
    )
    fecha = fields.Date(string='Fecha', required=True, default=fields.Date.today)
    granja_id = fields.Many2one('avicola.granja', string='Granja', required=True)
    galpon_id = fields.Many2one(
        'avicola.galpon', string='Galpón', required=True,
        domain="[('granja_id', '=', granja_id)]"
    )
    cantidad = fields.Integer(string='Cantidad Mortalidad', required=True)
    observaciones = fields.Text(string='Observaciones')
    estado = fields.Selection(
        [('borrador', 'Borrador'), ('confirmado', 'Confirmado')],
        string='Estado', default='borrador', required=True
    )

    @api.depends('galpon_id')
    def _compute_lote_incubadora(self):
        for rec in self:
            if rec.galpon_id:
                dist = self.env['avicola.distribucion'].search([
                    ('galpon_id', '=', rec.galpon_id.id),
                    ('estado', '=', 'confirmado')
                ], order='fecha desc, id desc', limit=1)
                rec.lote_incubadora = dist.lote_incubadora if dist else False
            else:
                rec.lote_incubadora = False

    def action_confirmar(self):
        for rec in self:
            if rec.estado == 'confirmado':
                raise UserError('Este registro ya está confirmado.')
            if not rec.galpon_id:
                raise UserError('Debe seleccionar un galpón.')
            if rec.cantidad <= 0:
                raise UserError('La cantidad debe ser mayor a cero.')
            if rec.galpon_id.cantidad_actual < rec.cantidad:
                raise UserError(
                    f'No hay suficientes aves en el galpón para registrar esta mortalidad. '
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
    _order = 'fecha desc, id desc'

    fecha = fields.Date(string='Fecha', required=True, default=fields.Date.today)
    granja_id = fields.Many2one('avicola.granja', string='Granja', required=True)
    galpon_id = fields.Many2one(
        'avicola.galpon', string='Galpón',
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
            if rec.galpon_id:
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
            if rec.estado == 'confirmado' and rec.galpon_id:
                rec.galpon_id.cantidad_actual += rec.cantidad
            rec.estado = 'borrador'


class AvicolaVeterinario(models.Model):
    _name = 'avicola.veterinario'
    _description = 'Veterinario'
    _order = 'name'

    name = fields.Char(string='Nombre', required=True)
    user_id = fields.Many2one('res.users', string='Usuario', help='Usuario asociado al veterinario')
    granja_ids = fields.Many2many('avicola.granja', string='Granjas Asignadas')
    active = fields.Boolean(string='Activo', default=True)

    @api.onchange('user_id')
    def _onchange_user_id(self):
        for rec in self:
            if rec.user_id:
                rec.name = rec.user_id.name

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('user_id'):
                existing = self.search([('user_id', '=', vals['user_id'])], limit=1)
                if existing:
                    raise UserError('Este usuario ya está asignado a otro veterinario.')
                if not vals.get('name'):
                    user = self.env['res.users'].browse(vals['user_id'])
                    vals['name'] = user.name or user.login
        records = super().create(vals_list)
        try:
            vet_group = self.env.ref('gestion_avicola.group_veterinario', raise_if_not_found=False)
        except Exception:
            vet_group = None
        if vet_group:
            for rec in records:
                if rec.user_id and vet_group not in rec.user_id.all_group_ids:
                    rec.user_id.sudo().write({'group_ids': [(4, vet_group.id)]})
        return records

    def write(self, vals):
        res = super().write(vals)
        try:
            vet_group = self.env.ref('gestion_avicola.group_veterinario', raise_if_not_found=False)
        except Exception:
            vet_group = None
        if vet_group and 'user_id' in vals:
            for rec in self:
                if rec.user_id and vet_group not in rec.user_id.all_group_ids:
                    rec.user_id.sudo().write({'group_ids': [(4, vet_group.id)]})
        return res


class AvicolaPlanVacunacion(models.Model):
    _name = 'avicola.plan.vacunacion'
    _description = 'Planificación de Vacunación'
    _order = 'fecha_planificada desc, id desc'

    name = fields.Char(string='Referencia', default='Plan de Vacunación', required=True)
    veterinario_id = fields.Many2one(
        'avicola.veterinario', string='Veterinario', required=True,
        default=lambda self: self._default_veterinario()
    )
    granja_id = fields.Many2one('avicola.granja', string='Granja', required=True)
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

    @api.onchange('veterinario_id')
    def _onchange_veterinario_id(self):
        for rec in self:
            if rec.veterinario_id and rec.veterinario_id.granja_ids:
                allowed = rec.veterinario_id.granja_ids.ids
                if rec.granja_id and rec.granja_id.id not in allowed:
                    rec.granja_id = False
                return {'domain': {'granja_id': [('id', 'in', allowed)]}}
            else:
                return {'domain': {'granja_id': []}}

    def action_programar(self):
        for rec in self:
            rec.state = 'programado'

    def action_realizar(self):
        for rec in self:
            rec.state = 'realizado'

    def write(self, vals):
        if 'veterinario_id' in vals and not self.env.user.has_group('base.group_system'):
            vet = self.env['avicola.veterinario'].search([('user_id', '=', self.env.uid)], limit=1)
            if vet:
                for rec in self:
                    if rec.veterinario_id and vals.get('veterinario_id') and rec.veterinario_id.id != vals.get('veterinario_id'):
                        raise UserError('No tienes permiso para cambiar el Veterinario.')
        return super().write(vals)


class AvicolaDespacho(models.Model):
    _name = 'avicola.despacho'
    _description = 'Despacho de Aves Vivas'
    _order = 'fecha desc, id desc'

    name = fields.Char(string='Número de Ticket', required=True, copy=False, readonly=True, default=lambda self: self._generate_sequence())
    
    # Datos fijos
    company_name = fields.Char(string='Empresa', default='DESPACHO AVES VIVAS\nAgrolucha, C.A.', readonly=True)
    company_rif = fields.Char(string='RIF', default='J-00089080-3', readonly=True)
    company_direccion = fields.Text(string='Dirección', default='Av. Las Delicias, Edf. Banvenez, piso Mzz 2 of. Mzz2, Urb. El Bosque Maracay Aragua.', readonly=True)

    # Datos de operación
    fecha = fields.Datetime(string='Fecha', default=fields.Datetime.now, required=True)
    granja = fields.Many2one('avicola.granja', string='Granja', required=True)
    galpon_id = fields.Many2one('avicola.galpon', string='Galpón', domain="[('granja_id', '=', granja)]")
    cliente = fields.Char(string='Cliente', required=True)
    placa = fields.Char(string='Placa del Vehículo')
    chofer = fields.Char(string='Nombre del Chofer')
    cant_jaulas = fields.Integer(string='Cant. Jaulas')
    pollos_por_jaula = fields.Integer(string='Pollos/jaula')
    orden_compra = fields.Char(string='Orden de compra Nro')
    inicio_carga = fields.Datetime(string='Inicio de carga')
    final_carga = fields.Datetime(string='Final de carga')
    cuadrilla = fields.Char(string='Cuadrilla')
    cantidad_aves = fields.Integer(string='Cant. Aves', required=True)
    peso_neto = fields.Float(string='Peso Neto (kg)', digits=(12, 2))
    peso_promedio = fields.Float(string='Peso Promedio (kg)', compute='_compute_peso_promedio', store=True, digits=(10, 3))
    pollo_mojado = fields.Selection([('si', 'Sí'), ('no', 'No')], string='Pollo mojado', default='no')
    precinto_1 = fields.Char(string='Precinto 1')
    precinto_2 = fields.Char(string='Precinto 2')
    precinto = fields.Char(string='Precinto')
    supervisor = fields.Many2one('res.users', string='Supervisor', default=lambda self: self.env.user)
    estado = fields.Selection([
        ('borrador', 'Borrador'),
        ('confirmado', 'Confirmado'),
        ('cancelado', 'Cancelado')
    ], string='Estado', default='borrador', required=True)
    salida_id = fields.Many2one('avicola.salida', string='Salida relacionada', ondelete='set null', readonly=True)

    @api.model
    def _generate_sequence(self):
        count = self.search_count([]) + 1
        return f"DSP-{fields.Date.today().strftime('%Y%m')}-{count:04d}"

    @api.depends('peso_neto', 'cantidad_aves')
    def _compute_peso_promedio(self):
        for rec in self:
            if rec.cantidad_aves and rec.cantidad_aves > 0:
                rec.peso_promedio = float(rec.peso_neto or 0.0) / float(rec.cantidad_aves)
            else:
                rec.peso_promedio = 0.0

    def action_confirm_despacho(self):
        for rec in self:
            if rec.estado == 'confirmado':
                raise UserError('Esta salida a matadero ya está confirmada.')
            if rec.cantidad_aves <= 0:
                raise UserError('La cantidad de aves debe ser mayor a cero.')
            
            # Descontar del galpón
            if rec.galpon_id:
                if rec.galpon_id.cantidad_actual < rec.cantidad_aves:
                    raise UserError(
                        f'No hay suficientes aves en el galpón {rec.galpon_id.name}. '
                        f'Disponibles: {rec.galpon_id.cantidad_actual}, '
                        f'Solicitadas: {rec.cantidad_aves}'
                    )
                rec.galpon_id.cantidad_actual -= rec.cantidad_aves

            rec.estado = 'confirmado'

    def action_borrador(self):
        for rec in self:
            if rec.estado == 'confirmado':
                if rec.galpon_id:
                    rec.galpon_id.cantidad_actual += rec.cantidad_aves
            rec.estado = 'borrador'

    def action_cancelar(self):
        for rec in self:
            if rec.estado == 'confirmado':
                if rec.galpon_id:
                    rec.galpon_id.cantidad_actual += rec.cantidad_aves
            rec.estado = 'cancelado'

    def action_print_ticket(self):
        self.ensure_one()
        return self.env.ref('gestion_avicola.action_report_ticket_despacho').report_action(self)


class AvicolaDashboard(models.Model):
    _name = 'avicola.dashboard'
    _description = 'Panel de Control Avícola'

    name = fields.Char(string="Dashboard", default="Panel de Control Avícola")
    selected_granja_id = fields.Many2one('avicola.granja', string='Filtrar por Granja')
    
    total_granjas = fields.Integer(string='Total Granjas', compute='_compute_metrics')
    total_galpones = fields.Integer(string='Total Galpones', compute='_compute_metrics')
    total_aves = fields.Integer(string='Población Actual de Aves', compute='_compute_metrics')
    capacidad_total = fields.Integer(string='Capacidad Total', compute='_compute_metrics')
    ocupacion_percent = fields.Float(string='Ocupación (%)', compute='_compute_metrics', digits=(10, 1))
    total_veterinarios = fields.Integer(string='Veterinarios Activos', compute='_compute_metrics')
    total_ingresos_pollitos = fields.Integer(string='Pollitos Ingresados', compute='_compute_metrics')
    total_salidas_matadero = fields.Integer(string='Aves Despachadas', compute='_compute_metrics')
    peso_total_despachado = fields.Float(string='Total Kilos Despachados (kg)', compute='_compute_metrics', digits=(10, 2))
    mortalidad_percent = fields.Float(string='Mortalidad (%)', compute='_compute_mortalidad_percent', digits=(10, 2))

    dashboard_html = fields.Html(
        string='Dashboard HTML',
        compute='_compute_dashboard_html',
        sanitize=False,
    )

    def _get_visible_granjas(self):
        if self.selected_granja_id:
            return self.selected_granja_id
        veterinarian = self.env['avicola.veterinario'].search([
            ('user_id', '=', self.env.uid),
        ], limit=1)
        if veterinarian and veterinarian.granja_ids:
            return veterinarian.granja_ids
        return self.env['avicola.granja'].search([])

    def _compute_metrics(self):
        Dist = self.env['avicola.distribucion']
        Salida = self.env['avicola.salida']
        Despacho = self.env['avicola.despacho']

        for rec in self:
            visible_granjas = rec._get_visible_granjas()
            rec.total_granjas = len(visible_granjas)

            galpones = self.env['avicola.galpon'].search([
                ('granja_id', 'in', visible_granjas.ids)
            ]) if visible_granjas else self.env['avicola.galpon'].browse([])
            rec.total_galpones = len(galpones)
            rec.total_aves = sum(galpones.mapped('cantidad_actual'))
            rec.capacidad_total = sum(galpones.mapped('capacidad_maxima'))
            if rec.capacidad_total > 0:
                rec.ocupacion_percent = (rec.total_aves * 100.0) / rec.capacidad_total
            else:
                rec.ocupacion_percent = 0.0

            granja_domain = [('granja_id', 'in', visible_granjas.ids)] if visible_granjas else []
            granja_desp_domain = [('granja', 'in', visible_granjas.ids)] if visible_granjas else []

            rec.total_ingresos_pollitos = sum(
                Dist.search([('estado', '=', 'confirmado')] + granja_domain).mapped('cantidad')
            )

            salidas_confirmadas = Salida.search([('estado', '=', 'confirmado')] + granja_domain)
            despachos_confirmados = Despacho.search([('estado', '=', 'confirmado')] + granja_desp_domain)
            
            cant_salidas = sum(salidas_confirmadas.mapped('cantidad'))
            cant_despachos = sum(despachos_confirmados.mapped('cantidad_aves'))
            rec.total_salidas_matadero = cant_salidas or cant_despachos

            peso_salidas = sum(salidas_confirmadas.mapped('peso_total'))
            peso_despachos = sum(despachos_confirmados.mapped('peso_neto'))
            rec.peso_total_despachado = peso_salidas or peso_despachos

            rec.total_veterinarios = self.env['avicola.veterinario'].search_count([])

    @api.depends('selected_granja_id')
    def _compute_mortalidad_percent(self):
        for rec in self:
            Dist = self.env['avicola.distribucion']
            Mort = self.env['avicola.mortalidad']
            domain = [('estado', '=', 'confirmado')]
            if rec.selected_granja_id:
                domain.append(('granja_id', '=', rec.selected_granja_id.id))
            
            total_ingresos = sum(Dist.search(domain).mapped('cantidad'))
            total_mortalidad = sum(Mort.search(domain).mapped('cantidad'))

            if total_ingresos > 0:
                rec.mortalidad_percent = (float(total_mortalidad) * 100.0) / float(total_ingresos)
            else:
                rec.mortalidad_percent = 0.0

    def _compute_dashboard_html(self):
        for rec in self:
            rec._compute_metrics()
            rec._compute_mortalidad_percent()

            visible_granjas = rec._get_visible_granjas()
            galpones = self.env['avicola.galpon'].search([
                ('granja_id', 'in', visible_granjas.ids)
            ]) if visible_granjas else self.env['avicola.galpon'].search([])

            # Determine if database has real records or if we show demo layout
            is_empty = (len(galpones) == 0 and rec.total_granjas == 0)

            total_aves = rec.total_aves if not is_empty else 48500
            total_galpones = rec.total_galpones if not is_empty else 10
            galpones_activos = len(galpones.filtered(lambda g: g.cantidad_actual > 0)) if not is_empty else 8
            pollitos = rec.total_ingresos_pollitos if not is_empty else 54000
            despachos_count = rec.total_salidas_matadero if not is_empty else 14
            peso_despachado = rec.peso_total_despachado if not is_empty else 28450.0
            ocupacion_pct = rec.ocupacion_percent if not is_empty and rec.ocupacion_percent > 0 else 74.0
            mortalidad_pct = rec.mortalidad_percent if not is_empty and rec.mortalidad_percent > 0 else 1.25

            # Gauge SVG
            r = 75
            dash_total = 235.6
            pct_val = max(0, min(100, ocupacion_pct))
            dash_fill = (pct_val / 100.0) * dash_total
            dash_empty = dash_total - dash_fill
            gauge_svg = f"""
            <svg viewBox="0 0 200 115" style="width: 100%; max-width: 200px; margin: 0 auto; display: block;">
                <defs>
                    <linearGradient id="gaugeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                        <stop offset="0%" stop-color="#34D399" />
                        <stop offset="100%" stop-color="#144D34" />
                    </linearGradient>
                </defs>
                <path d="M 25 100 A 75 75 0 0 1 175 100" fill="none" stroke="#e2e8f0" stroke-width="18" stroke-linecap="round" />
                <path d="M 25 100 A 75 75 0 0 1 175 100" fill="none" stroke="url(#gaugeGrad)" stroke-width="18" stroke-linecap="round"
                      stroke-dasharray="{dash_fill:.1f} {dash_empty:.1f}" />
                <text x="100" y="80" text-anchor="middle" font-size="32" font-weight="800" fill="#0f172a" font-family="-apple-system, sans-serif">{int(pct_val)}%</text>
                <text x="100" y="98" text-anchor="middle" font-size="11" font-weight="600" fill="#64748b" font-family="-apple-system, sans-serif">Capacidad Ocupada</text>
            </svg>
            """

            # Galpones Capsule Bars Data (matching "Project Analytics")
            bar_items = []
            if not is_empty and galpones:
                sample_galpones = galpones[:7]
                for i, g in enumerate(sample_galpones):
                    cap = g.capacidad_maxima or 10000
                    h_pct = min(100, max(15, int((g.cantidad_actual / cap) * 100)))
                    label = g.name.replace('Galpón ', 'G').replace('Galpon ', 'G')[:4]
                    bar_items.append((label, h_pct, i == 3))
            else:
                bar_items = [
                    ('G1', 45, False),
                    ('G2', 78, False),
                    ('G3', 60, False),
                    ('G4', 88, True),
                    ('G5', 52, False),
                    ('G6', 68, False),
                    ('G7', 40, False),
                ]

            bars_html = ""
            for label, h_pct, is_peak in bar_items:
                if is_peak:
                    bar_bg = "#144D34"
                    badge_html = f"""<div style="background: #ffffff; border: 1px solid #cbd5e1; border-radius: 999px; padding: 1px 7px; font-size: 10px; font-weight: 700; color: #144D34; box-shadow: 0 2px 4px rgba(0,0,0,0.06); margin-bottom: 4px;">{h_pct}%</div>"""
                elif h_pct > 65:
                    bar_bg = "#34D399"
                    badge_html = """<div style="height: 18px;"></div>"""
                else:
                    bar_bg = "repeating-linear-gradient(45deg, #cbd5e1, #cbd5e1 3px, #e2e8f0 3px, #e2e8f0 7px)"
                    badge_html = """<div style="height: 18px;"></div>"""

                bars_html += f"""
                <div style="display: flex; flex-direction: column; align-items: center; justify-content: flex-end; height: 160px; width: 14%;">
                    {badge_html}
                    <div style="width: 28px; height: {h_pct}%; background: {bar_bg}; border-radius: 999px; transition: height 0.3s ease;"></div>
                    <span style="font-size: 11px; font-weight: 600; color: #64748b; margin-top: 8px;">{label}</span>
                </div>
                """

            # Recent Despachos / Actividades (matching "Project")
            despachos_recientes = self.env['avicola.despacho'].search([], limit=5, order='fecha desc')
            recent_items_html = ""
            if despachos_recientes:
                icon_colors = ["#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#ec4899"]
                for i, d in enumerate(despachos_recientes):
                    c = icon_colors[i % len(icon_colors)]
                    date_str = d.fecha.strftime('%d/%m/%Y') if d.fecha else 'Hoy'
                    st = dict(d._fields['estado'].selection).get(d.estado, d.estado)
                    st_bg = "#dcfce7" if d.estado == 'confirmado' else "#fef3c7" if d.estado == 'borrador' else "#fee2e2"
                    st_color = "#15803d" if d.estado == 'confirmado' else "#b45309" if d.estado == 'borrador' else "#b91c1c"
                    recent_items_html += f"""
                    <div style="display: flex; align-items: center; justify-content: space-between; padding: 9px 0; border-bottom: 1px solid #f1f5f9;">
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <div style="width: 30px; height: 30px; border-radius: 8px; background: {c}15; color: {c}; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: bold;">
                                <i class="fa fa-truck"></i>
                            </div>
                            <div>
                                <div style="font-size: 13px; font-weight: 600; color: #0f172a;">{d.name} • {html.escape(d.cliente or 'Cliente')}</div>
                                <div style="font-size: 11px; color: #64748b;">{date_str} • {d.cantidad_aves} aves • {d.peso_neto:,.0f} kg</div>
                            </div>
                        </div>
                        <span style="background: {st_bg}; color: {st_color}; padding: 3px 8px; border-radius: 999px; font-size: 11px; font-weight: 600;">{st}</span>
                    </div>
                    """
            else:
                demo_projects = [
                    ('Ticket DSP-202610-001', 'Matadero Central C.A. • 3,200 aves', 'Hoy', 'Confirmado', '#3b82f6', '#dcfce7', '#15803d'),
                    ('Distribución Lote INC-44', 'Granja Los Pinos • 12,000 BB', '26/10', 'Completado', '#10b981', '#dcfce7', '#15803d'),
                    ('Despacho Aves Vivas', 'Distribuidora El Pollo • 2,400 aves', '25/10', 'En Carga', '#f59e0b', '#fef3c7', '#b45309'),
                    ('Lote Incubadora 42', 'Galpón 03 • 9,500 pollitos', '24/10', 'Confirmado', '#8b5cf6', '#dcfce7', '#15803d'),
                    ('Plan de Vacunación', 'Control Newcastle Galpón 01', '23/10', 'Realizado', '#06b6d4', '#e0f2fe', '#0369a1'),
                ]
                for title, sub, dt, st, ic, sbg, scolor in demo_projects:
                    recent_items_html += f"""
                    <div style="display: flex; align-items: center; justify-content: space-between; padding: 9px 0; border-bottom: 1px solid #f1f5f9;">
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <div style="width: 30px; height: 30px; border-radius: 8px; background: {ic}15; color: {ic}; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: bold;">
                                <i class="fa fa-tag"></i>
                            </div>
                            <div>
                                <div style="font-size: 13px; font-weight: 600; color: #0f172a;">{title}</div>
                                <div style="font-size: 11px; color: #64748b;">{sub} • {dt}</div>
                            </div>
                        </div>
                        <span style="background: {sbg}; color: {scolor}; padding: 3px 8px; border-radius: 999px; font-size: 11px; font-weight: 600;">{st}</span>
                    </div>
                    """

            # Team members (Veterinarians / Supervisors)
            vets = self.env['avicola.veterinario'].search([], limit=4)
            team_html = ""
            if vets:
                avatars = [('CR', '#10b981'), ('EM', '#3b82f6'), ('MT', '#f59e0b'), ('JA', '#8b5cf6')]
                for i, v in enumerate(vets):
                    init, bg = avatars[i % len(avatars)]
                    farm_names = ", ".join(v.granja_ids.mapped('name')) if v.granja_ids else "Todas las granjas"
                    team_html += f"""
                    <div style="display: flex; align-items: center; justify-content: space-between; padding: 9px 0; border-bottom: 1px solid #f1f5f9;">
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <div style="width: 34px; height: 34px; border-radius: 50%; background: {bg}; color: white; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: bold;">{init}</div>
                            <div>
                                <div style="font-size: 13px; font-weight: 600; color: #0f172a;">{v.name}</div>
                                <div style="font-size: 11px; color: #64748b;">Salud Aviar • {farm_names}</div>
                            </div>
                        </div>
                        <span style="background: #ecfdf5; color: #059669; border: 1px solid #a7f3d0; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 500;">Activo</span>
                    </div>
                    """
            else:
                demo_team = [
                    ('Dr. Carlos Rodríguez', 'Salud Aviar • Granja Los Pinos', 'CR', '#10b981', 'Activo', '#ecfdf5', '#059669'),
                    ('Dra. Elena Morales', 'Bioseguridad • Granja Valle Verde', 'EM', '#3b82f6', 'En Campo', '#eff6ff', '#2563eb'),
                    ('Ing. Miguel Torres', 'Supervisor de Carga y Pesaje', 'MT', '#f59e0b', 'Activo', '#fefce8', '#ca8a04'),
                    ('Dr. Juan Arana', 'Dirección Técnica y Sanitaria', 'JA', '#8b5cf6', 'Disponible', '#faf5ff', '#7c3aed'),
                ]
                for name, role, init, bg, tag, tbg, tcolor in demo_team:
                    team_html += f"""
                    <div style="display: flex; align-items: center; justify-content: space-between; padding: 9px 0; border-bottom: 1px solid #f1f5f9;">
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <div style="width: 34px; height: 34px; border-radius: 50%; background: {bg}; color: white; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: bold;">{init}</div>
                            <div>
                                <div style="font-size: 13px; font-weight: 600; color: #0f172a;">{name}</div>
                                <div style="font-size: 11px; color: #64748b;">{role}</div>
                            </div>
                        </div>
                        <span style="background: {tbg}; color: {tcolor}; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 500;">{tag}</span>
                    </div>
                    """

            # Demo banner if empty
            demo_banner_html = ""
            if is_empty:
                demo_banner_html = """
                <div style="background: linear-gradient(135deg, #144D34 0%, #1a6344 100%); border-radius: 16px; padding: 14px 20px; color: white; margin-bottom: 24px; display: flex; align-items: center; justify-content: space-between; box-shadow: 0 4px 12px rgba(20,77,52,0.15);">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <span style="font-size: 20px;">🐔</span>
                        <div>
                            <strong style="font-size: 14px;">Bienvenido a Gestión Avícola</strong>
                            <div style="font-size: 12px; opacity: 0.9;">Mostrando métricas proyectadas. Haz clic en "Cargar Datos Demo" para poblar el sistema con granjas y lotes reales de prueba.</div>
                        </div>
                    </div>
                    <button type="object" name="action_load_demo_data" class="btn btn-sm" style="background: #ffffff; color: #144D34; font-weight: 700; border-radius: 999px; padding: 6px 16px; border: none; font-size: 12px;">
                        ⚡ Cargar Datos Demo
                    </button>
                </div>
                """

            rec.dashboard_html = f"""
            <div style="background: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; padding: 20px; border-radius: 20px; color: #0f172a;">
                
                {demo_banner_html}

                <!-- TOP HEADER -->
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; flex-wrap: wrap; gap: 12px;">
                    <div>
                        <h1 style="font-size: 28px; font-weight: 800; color: #0f172a; margin: 0 0 4px 0; letter-spacing: -0.5px;">Dashboard</h1>
                        <p style="font-size: 13px; color: #64748b; margin: 0;">Planifica, supervisa y optimiza tus operaciones avícolas con facilidad.</p>
                    </div>
                    <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
                        <button type="object" name="action_new_despacho" class="btn btn-sm" style="background: #144D34; color: #ffffff; border-radius: 999px; padding: 8px 18px; font-weight: 600; font-size: 13px; border: none; display: inline-flex; align-items: center; gap: 6px; box-shadow: 0 4px 10px rgba(20,77,52,0.2);">
                            <i class="fa fa-plus"></i> Nuevo Despacho
                        </button>
                        <button type="object" name="action_new_distribucion" class="btn btn-sm" style="background: #ffffff; color: #0f172a; border: 1.5px solid #cbd5e1; border-radius: 999px; padding: 8px 18px; font-weight: 600; font-size: 13px; display: inline-flex; align-items: center; gap: 6px;">
                            <i class="fa fa-truck"></i> Distribuir Pollitos
                        </button>
                        <button type="object" name="action_load_demo_data" class="btn btn-sm" style="background: #ffffff; color: #144D34; border: 1.5px solid #a7f3d0; border-radius: 999px; padding: 8px 14px; font-weight: 600; font-size: 13px; display: inline-flex; align-items: center; gap: 5px;">
                            <i class="fa fa-bolt" style="color: #10b981;"></i> Demo
                        </button>
                    </div>
                </div>

                <!-- TOP 4 KPI CARDS -->
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px;">
                    
                    <!-- Card 1: Total Aves (Dark Forest Green) -->
                    <div style="background-color: #144D34; border-radius: 18px; padding: 22px; color: #ffffff; position: relative; display: flex; flex-direction: column; justify-content: space-between; min-height: 140px; box-shadow: 0 6px 16px rgba(20,77,52,0.18);">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-size: 13px; font-weight: 600; color: #a7f3d0;">Población Total Aves</span>
                            <button type="object" name="action_open_galpones" style="width: 32px; height: 32px; border-radius: 50%; border: 1.5px solid rgba(255,255,255,0.4); background: transparent; display: flex; align-items: center; justify-content: center; font-size: 14px; color: #ffffff; cursor: pointer;">↗</button>
                        </div>
                        <div style="font-size: 34px; font-weight: 800; line-height: 1; margin: 14px 0; color: #ffffff;">{total_aves:,.0f}</div>
                        <div>
                            <span style="background: rgba(255,255,255,0.18); color: #ffffff; padding: 4px 10px; border-radius: 999px; font-size: 11px; font-weight: 600; display: inline-flex; align-items: center; gap: 4px;">
                                <span>↗</span> {ocupacion_pct:.0f}% Capacidad Ocupada
                            </span>
                        </div>
                    </div>

                    <!-- Card 2: Galpones Activos -->
                    <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 18px; padding: 22px; color: #0f172a; position: relative; display: flex; flex-direction: column; justify-content: space-between; min-height: 140px; box-shadow: 0 2px 6px rgba(0,0,0,0.02);">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-size: 13px; font-weight: 600; color: #64748b;">Galpones Activos</span>
                            <button type="object" name="action_open_galpones" style="width: 32px; height: 32px; border-radius: 50%; border: 1.5px solid #e2e8f0; background: transparent; display: flex; align-items: center; justify-content: center; font-size: 14px; color: #334155; cursor: pointer;">↗</button>
                        </div>
                        <div style="font-size: 34px; font-weight: 800; line-height: 1; margin: 14px 0; color: #0f172a;">{galpones_activos}</div>
                        <div>
                            <span style="background: #f1f5f9; color: #475569; padding: 4px 10px; border-radius: 999px; font-size: 11px; font-weight: 600;">
                                de {total_galpones} Galpones Totales
                            </span>
                        </div>
                    </div>

                    <!-- Card 3: Pollitos Ingresados -->
                    <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 18px; padding: 22px; color: #0f172a; position: relative; display: flex; flex-direction: column; justify-content: space-between; min-height: 140px; box-shadow: 0 2px 6px rgba(0,0,0,0.02);">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-size: 13px; font-weight: 600; color: #64748b;">Pollitos Ingresados</span>
                            <button type="object" name="action_open_distribuciones" style="width: 32px; height: 32px; border-radius: 50%; border: 1.5px solid #e2e8f0; background: transparent; display: flex; align-items: center; justify-content: center; font-size: 14px; color: #334155; cursor: pointer;">↗</button>
                        </div>
                        <div style="font-size: 34px; font-weight: 800; line-height: 1; margin: 14px 0; color: #0f172a;">{pollitos:,.0f}</div>
                        <div>
                            <span style="background: #f1f5f9; color: #475569; padding: 4px 10px; border-radius: 999px; font-size: 11px; font-weight: 600;">
                                Lotes de Incubadora
                            </span>
                        </div>
                    </div>

                    <!-- Card 4: Despachos Matadero -->
                    <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 18px; padding: 22px; color: #0f172a; position: relative; display: flex; flex-direction: column; justify-content: space-between; min-height: 140px; box-shadow: 0 2px 6px rgba(0,0,0,0.02);">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-size: 13px; font-weight: 600; color: #64748b;">Despachos Matadero</span>
                            <button type="object" name="action_open_salidas" style="width: 32px; height: 32px; border-radius: 50%; border: 1.5px solid #e2e8f0; background: transparent; display: flex; align-items: center; justify-content: center; font-size: 14px; color: #334155; cursor: pointer;">↗</button>
                        </div>
                        <div style="font-size: 34px; font-weight: 800; line-height: 1; margin: 14px 0; color: #0f172a;">{despachos_count}</div>
                        <div>
                            <span style="background: #f1f5f9; color: #475569; padding: 4px 10px; border-radius: 999px; font-size: 11px; font-weight: 600;">
                                {peso_despachado:,.0f} kg despachados
                            </span>
                        </div>
                    </div>

                </div>

                <!-- MIDDLE SECTION -->
                <div style="display: grid; grid-template-columns: repeat(12, 1fr); gap: 16px; margin-bottom: 24px;">
                    
                    <!-- Middle Left: Project Analytics (Ocupación Galpones) -->
                    <div style="grid-column: span 5; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 18px; padding: 22px; box-shadow: 0 2px 6px rgba(0,0,0,0.02); display: flex; flex-direction: column; justify-content: space-between;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                            <div>
                                <h3 style="font-size: 15px; font-weight: 700; color: #0f172a; margin: 0;">Ocupación por Galpón</h3>
                                <div style="font-size: 12px; color: #64748b;">Nivel de carga y capacidad por nave</div>
                            </div>
                            <button type="object" name="action_open_galpones" class="btn btn-link p-0 text-decoration-none" style="font-size: 12px; font-weight: 600; color: #144D34;">Ver Gráfica →</button>
                        </div>
                        <div style="display: flex; justify-content: space-around; align-items: flex-end; height: 160px; padding-top: 10px;">
                            {bars_html}
                        </div>
                    </div>

                    <!-- Middle Center: Reminders / Próxima Actividad -->
                    <div style="grid-column: span 3; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 18px; padding: 22px; box-shadow: 0 2px 6px rgba(0,0,0,0.02); display: flex; flex-direction: column; justify-content: space-between;">
                        <div>
                            <span style="font-size: 11px; font-weight: 700; color: #144D34; text-transform: uppercase; letter-spacing: 0.5px;">Recordatorio Operativo</span>
                            <h3 style="font-size: 16px; font-weight: 700; color: #0f172a; margin: 8px 0 4px 0;">Vacunación Newcastle</h3>
                            <div style="font-size: 12px; color: #64748b;">Galpón 02 • Granja Los Pinos</div>
                            <div style="display: inline-flex; align-items: center; gap: 6px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 6px 10px; margin-top: 14px; font-size: 12px; color: #334155; font-weight: 500;">
                                <i class="fa fa-clock-o text-muted"></i> Mañana 08:30 am
                            </div>
                        </div>
                        <div style="margin-top: 20px;">
                            <button type="object" name="action_open_planificaciones" class="btn w-100" style="background: #144D34; color: white; border-radius: 12px; padding: 10px; font-weight: 600; font-size: 13px; border: none; box-shadow: 0 4px 10px rgba(20,77,52,0.15);">
                                <i class="fa fa-calendar-check-o me-1"></i> Ver Planificación
                            </button>
                        </div>
                    </div>

                    <!-- Middle Right: Recent Despachos / Projects -->
                    <div style="grid-column: span 4; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 18px; padding: 22px; box-shadow: 0 2px 6px rgba(0,0,0,0.02);">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                            <h3 style="font-size: 15px; font-weight: 700; color: #0f172a; margin: 0;">Despachos Recientes</h3>
                            <button type="object" name="action_new_despacho" class="btn btn-sm" style="background: #f1f5f9; color: #0f172a; border-radius: 999px; font-weight: 600; font-size: 11px; padding: 3px 10px; border: none;">+ Nuevo</button>
                        </div>
                        <div>
                            {recent_items_html}
                        </div>
                    </div>

                </div>

                <!-- BOTTOM SECTION -->
                <div style="display: grid; grid-template-columns: repeat(12, 1fr); gap: 16px;">
                    
                    <!-- Bottom Left: Team Collaboration (Veterinarios) -->
                    <div style="grid-column: span 5; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 18px; padding: 22px; box-shadow: 0 2px 6px rgba(0,0,0,0.02);">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                            <h3 style="font-size: 15px; font-weight: 700; color: #0f172a; margin: 0;">Equipo Veterinario y Campo</h3>
                            <button type="object" name="action_open_veterinarios" class="btn btn-sm" style="background: #f1f5f9; color: #0f172a; border-radius: 999px; font-weight: 600; font-size: 11px; padding: 3px 10px; border: none;">+ Asignar</button>
                        </div>
                        <div>
                            {team_html}
                        </div>
                    </div>

                    <!-- Bottom Center: Project Progress (Gauge Semi-circle) -->
                    <div style="grid-column: span 4; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 18px; padding: 22px; box-shadow: 0 2px 6px rgba(0,0,0,0.02); display: flex; flex-direction: column; justify-content: space-between;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                            <h3 style="font-size: 15px; font-weight: 700; color: #0f172a; margin: 0;">Capacidad & Ocupación</h3>
                            <span style="font-size: 11px; color: #64748b;">Global</span>
                        </div>
                        <div>
                            {gauge_svg}
                        </div>
                        <div style="display: flex; justify-content: center; gap: 14px; margin-top: 10px; font-size: 11px; color: #475569; font-weight: 500; flex-wrap: wrap;">
                            <span style="display: inline-flex; align-items: center; gap: 5px;">
                                <span style="width: 8px; height: 8px; border-radius: 50%; background: #144D34;"></span> En Engorde ({ocupacion_pct:.0f}%)
                            </span>
                            <span style="display: inline-flex; align-items: center; gap: 5px;">
                                <span style="width: 8px; height: 8px; border-radius: 50%; background: #34D399;"></span> Despachado
                            </span>
                            <span style="display: inline-flex; align-items: center; gap: 5px;">
                                <span style="width: 8px; height: 8px; border-radius: 50%; background: #cbd5e1;"></span> Libre
                            </span>
                        </div>
                    </div>

                    <!-- Bottom Right: Time Tracker / Control Sanitario Dark Card -->
                    <div style="grid-column: span 3; background: radial-gradient(circle at 50% 120%, #1e5a3c 0%, #0c281a 60%, #06160e 100%); border-radius: 18px; padding: 22px; color: white; display: flex; flex-direction: column; justify-content: space-between; box-shadow: 0 6px 18px rgba(12,40,26,0.3); min-height: 200px;">
                        <div>
                            <span style="font-size: 11px; font-weight: 700; color: #a7f3d0; text-transform: uppercase; letter-spacing: 0.5px;">Control Sanitario</span>
                            <div style="font-size: 36px; font-weight: 800; letter-spacing: 0.5px; color: #ffffff; margin: 16px 0 6px 0;">{mortalidad_pct:.2f}%</div>
                            <div style="font-size: 12px; color: #d1fae5; opacity: 0.9;">Tasa de Mortalidad Acumulada</div>
                        </div>
                        <div style="display: flex; align-items: center; justify-content: space-between; margin-top: 16px; border-top: 1px solid rgba(255,255,255,0.15); padding-top: 12px;">
                            <span style="display: inline-flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 600; color: #a7f3d0;">
                                <i class="fa fa-check-circle"></i> Óptimo (&lt; 3.0%)
                            </span>
                            <span style="background: rgba(255,255,255,0.15); padding: 3px 8px; border-radius: 999px; font-size: 10px; font-weight: 600; color: #ffffff;">
                                Bioseguridad Activa
                            </span>
                        </div>
                    </div>

                </div>

            </div>
            """

    def action_load_demo_data(self):
        """Carga datos de demostración si el usuario quiere ver el sistema completamente poblado"""
        self.ensure_one()
        # Verificar si ya existen granjas demo
        granja_pinos = self.env['avicola.granja'].search([('name', '=', 'Granja Los Pinos')], limit=1)
        if not granja_pinos:
            granja_pinos = self.env['avicola.granja'].create({
                'name': 'Granja Los Pinos',
                'tipo': 'propia',
                'ubicacion': 'Sector La Morita, Valles del Tuy',
            })
            # Crear Galpones
            g1 = self.env['avicola.galpon'].create({'granja_id': granja_pinos.id, 'name': 'Galpón 01', 'metros_cuadrados': 1200.0, 'capacidad_maxima': 15000})
            g2 = self.env['avicola.galpon'].create({'granja_id': granja_pinos.id, 'name': 'Galpón 02', 'metros_cuadrados': 1000.0, 'capacidad_maxima': 12000})
            g3 = self.env['avicola.galpon'].create({'granja_id': granja_pinos.id, 'name': 'Galpón 03', 'metros_cuadrados': 800.0, 'capacidad_maxima': 10000})
            g4 = self.env['avicola.galpon'].create({'granja_id': granja_pinos.id, 'name': 'Galpón 04', 'metros_cuadrados': 1500.0, 'capacidad_maxima': 18000})

            # Distribuciones
            d1 = self.env['avicola.distribucion'].create({'lote_incubadora': 'INC-2026-101', 'fecha': fields.Date.today(), 'granja_id': granja_pinos.id, 'galpon_id': g1.id, 'cantidad': 14000})
            d1.action_confirmar()
            d2 = self.env['avicola.distribucion'].create({'lote_incubadora': 'INC-2026-102', 'fecha': fields.Date.today(), 'granja_id': granja_pinos.id, 'galpon_id': g2.id, 'cantidad': 11500})
            d2.action_confirmar()
            d3 = self.env['avicola.distribucion'].create({'lote_incubadora': 'INC-2026-103', 'fecha': fields.Date.today(), 'granja_id': granja_pinos.id, 'galpon_id': g3.id, 'cantidad': 9000})
            d3.action_confirmar()
            d4 = self.env['avicola.distribucion'].create({'lote_incubadora': 'INC-2026-104', 'fecha': fields.Date.today(), 'granja_id': granja_pinos.id, 'galpon_id': g4.id, 'cantidad': 16500})
            d4.action_confirmar()

            # Mortalidad controlada
            m1 = self.env['avicola.mortalidad'].create({'fecha': fields.Date.today(), 'granja_id': granja_pinos.id, 'galpon_id': g1.id, 'cantidad': 120, 'observaciones': 'Bajas normales primera semana'})
            m1.action_confirmar()
            m2 = self.env['avicola.mortalidad'].create({'fecha': fields.Date.today(), 'granja_id': granja_pinos.id, 'galpon_id': g2.id, 'cantidad': 85, 'observaciones': 'Control ambiental'})
            m2.action_confirmar()

            # Despachos a matadero
            dsp1 = self.env['avicola.despacho'].create({
                'granja': granja_pinos.id,
                'galpon_id': g1.id,
                'cliente': 'Matadero Avícola Central C.A.',
                'chofer': 'Carlos Mendoza',
                'placa': 'A34BC9D',
                'cuadrilla': 'Cuadrilla 1',
                'cant_jaulas': 220,
                'pollos_por_jaula': 15,
                'cantidad_aves': 3300,
                'peso_neto': 7260.0,
            })
            dsp1.action_confirm_despacho()

            dsp2 = self.env['avicola.despacho'].create({
                'granja': granja_pinos.id,
                'galpon_id': g3.id,
                'cliente': 'Distribuidora El Pollo Dorado',
                'chofer': 'Pedro Rivas',
                'placa': 'B78TY12',
                'cuadrilla': 'Cuadrilla 2',
                'cant_jaulas': 180,
                'pollos_por_jaula': 15,
                'cantidad_aves': 2700,
                'peso_neto': 5940.0,
            })
            dsp2.action_confirm_despacho()

        granja_valle = self.env['avicola.granja'].search([('name', '=', 'Granja Valle Verde')], limit=1)
        if not granja_valle:
            granja_valle = self.env['avicola.granja'].create({
                'name': 'Granja Valle Verde',
                'tipo': 'alquilada',
                'ubicacion': 'Sector El Sombrero, Guárico',
            })
            ga = self.env['avicola.galpon'].create({'granja_id': granja_valle.id, 'name': 'Galpón A', 'metros_cuadrados': 1000.0, 'capacidad_maxima': 12000})
            gb = self.env['avicola.galpon'].create({'granja_id': granja_valle.id, 'name': 'Galpón B', 'metros_cuadrados': 800.0, 'capacidad_maxima': 10000})

            da = self.env['avicola.distribucion'].create({'lote_incubadora': 'INC-2026-105', 'fecha': fields.Date.today(), 'granja_id': granja_valle.id, 'galpon_id': ga.id, 'cantidad': 11000})
            da.action_confirmar()

        # Crear Veterinarios demo si no existen
        if self.env['avicola.veterinario'].search_count([]) == 0:
            self.env['avicola.veterinario'].create({
                'name': 'Dr. Carlos Rodríguez',
                'granja_ids': [(6, 0, [granja_pinos.id])],
            })
            self.env['avicola.veterinario'].create({
                'name': 'Dra. Elena Morales',
                'granja_ids': [(6, 0, [granja_valle.id])],
            })
            self.env['avicola.veterinario'].create({
                'name': 'Ing. Miguel Torres',
                'granja_ids': [(6, 0, [granja_pinos.id, granja_valle.id])],
            })

        # Planificación
        if self.env['avicola.plan.vacunacion'].search_count([]) == 0:
            vet = self.env['avicola.veterinario'].search([], limit=1)
            self.env['avicola.plan.vacunacion'].create({
                'name': 'Vacunación Newcastle - Galpón 02',
                'granja_id': granja_pinos.id,
                'veterinario_id': vet.id,
                'fecha_planificada': fields.Date.today(),
                'descripcion': 'Dosis 1 vacuna viva liofilizada contra Newcastle y Bronquitis.',
                'state': 'programado',
            })

        self._compute_metrics()
        self._compute_mortalidad_percent()
        self._compute_dashboard_html()
        return True

    def action_new_despacho(self):
        return {
            'name': 'Nuevo Despacho',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.despacho',
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_granja': self.selected_granja_id.id if self.selected_granja_id else False},
        }

    def action_new_distribucion(self):
        return {
            'name': 'Nueva Distribución de Pollitos',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.distribucion',
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_granja_id': self.selected_granja_id.id if self.selected_granja_id else False},
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
            'view_mode': 'list,form,graph,pivot',
            'target': 'current',
        }

    def action_open_distribuciones(self):
        return {
            'name': 'Distribuciones',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.distribucion',
            'view_mode': 'list,form,graph',
            'target': 'current',
        }

    def action_open_mortalidad(self):
        domain = []
        if self.selected_granja_id:
            domain = [('granja_id', '=', self.selected_granja_id.id)]
        return {
            'name': 'Mortalidad de Aves',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.mortalidad',
            'view_mode': 'list,form,graph',
            'target': 'current',
            'domain': domain,
        }

    def action_open_salidas(self):
        return {
            'name': 'Despachos de Aves Vivas',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.despacho',
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


class ResUsers(models.Model):
    _inherit = 'res.users'

    def write(self, vals):
        res = super().write(vals)
        try:
            vet_group = self.env.ref('gestion_avicola.group_veterinario', raise_if_not_found=False)
        except Exception:
            vet_group = None
        if vet_group:
            for user in self:
                if vet_group in user.all_group_ids:
                    vet = self.env['avicola.veterinario'].search([('user_id', '=', user.id)], limit=1)
                    if not vet:
                        self.env['avicola.veterinario'].create({
                            'user_id': user.id,
                            'name': user.name or user.login,
                        })
        return res
