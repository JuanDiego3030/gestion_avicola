# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import timedelta
import math


class AvicolaProyeccionConfig(models.Model):
    _name = 'avicola.proyeccion.config'
    _description = 'Configuración de Parámetros de Proyecciones de Saca'

    name = fields.Char(string='Nombre de Perfil', default='Configuración Estándar de Saca', required=True)
    active = fields.Boolean(string='Activo', default=True)

    # Variables zootécnicas ajustables por el usuario
    edad_objetivo_dias = fields.Integer(
        string='Edad Objetivo de Saca (días)',
        default=42,
        required=True,
        help='Edad estándar en días a la que los lotes deben salir a matadero.'
    )
    peso_objetivo_kg = fields.Float(
        string='Peso Promedio Objetivo (kg/ave)',
        default=2.50,
        required=True,
        digits=(10, 2),
        help='Peso promedio en pie esperado por cada ave al momento del sacrificio.'
    )
    ganancia_diaria_gr = fields.Float(
        string='Ganancia Diaria Promedio (g/día)',
        default=59.5,
        required=True,
        digits=(10, 1),
        help='Ganancia promedio en gramos de peso vivo por ave cada día.'
    )
    mortalidad_estimada_pct = fields.Float(
        string='Mortalidad Estimada Acumulada (%)',
        default=3.50,
        required=True,
        digits=(10, 2),
        help='Porcentaje de bajas esperado durante el ciclo completo de engorde.'
    )
    ica_estimado = fields.Float(
        string='Índice Conversión Alimenticia (ICA)',
        default=1.65,
        required=True,
        digits=(10, 3),
        help='Kilos de alimento consumido requeridos para producir 1 kg de carne de pollo vivo.'
    )

    # Parámetros logísticos y de transporte
    pollos_por_jaula = fields.Integer(
        string='Aves por Jaula de Transporte',
        default=15,
        required=True,
        help='Capacidad recomendada de pollos vivos por huacal / jaula de carga.'
    )
    jaulas_por_camion = fields.Integer(
        string='Jaulas por Camión de Carga',
        default=220,
        required=True,
        help='Capacidad promedio de jaulas que puede transportar un camión o batea.'
    )
    dias_aviso_previo = fields.Integer(
        string='Aviso Previo de Saca (días)',
        default=7,
        required=True,
        help='Días antes de la fecha proyectada para clasificar el lote como Próximo a Sacar.'
    )

    # Parámetros económicos
    precio_estimado_kg = fields.Float(
        string='Precio de Venta Estimado ($/kg)',
        default=1.85,
        digits=(10, 2),
        help='Precio proyectado por kilogramo de pollo vivo en pie.'
    )
    notas = fields.Text(string='Notas Técnicas / Genética')

    @api.model
    def get_default_config(self):
        """Devuelve la configuración activa o crea una estándar si no existe."""
        config = self.search([('active', '=', True)], limit=1)
        if not config:
            config = self.create({
                'name': 'Configuración Estándar de Saca',
                'edad_objetivo_dias': 42,
                'peso_objetivo_kg': 2.50,
                'ganancia_diaria_gr': 59.5,
                'mortalidad_estimada_pct': 3.50,
                'ica_estimado': 1.65,
                'pollos_por_jaula': 15,
                'jaulas_por_camion': 220,
                'dias_aviso_previo': 7,
                'precio_estimado_kg': 1.85,
                'notas': 'Parámetros estándar para genética Cobb 500 / Ross 308 en condiciones tropicales.',
            })
        return config

    def action_aplicar_a_lotes_activos(self):
        """Aplica estos parámetros configurados a todos los lotes en engorde activos."""
        self.ensure_one()
        lotes_activos = self.env['avicola.proyeccion.lote'].search([
            ('estado', 'in', ['crecimiento', 'proximo', 'listo'])
        ])
        for lote in lotes_activos:
            lote.write({
                'config_id': self.id,
                'edad_objetivo_dias': self.edad_objetivo_dias,
                'peso_objetivo_kg': self.peso_objetivo_kg,
                'ganancia_diaria_gr': self.ganancia_diaria_gr,
                'mortalidad_estimada_pct': self.mortalidad_estimada_pct,
                'pollos_por_jaula': self.pollos_por_jaula,
                'jaulas_por_camion': self.jaulas_por_camion,
                'precio_estimado_kg': self.precio_estimado_kg,
            })
            lote._compute_proyeccion()
            lote._compute_estado()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Configuración Aplicada',
                'message': f'Se actualizaron {len(lotes_activos)} proyecciones de lotes activos con los nuevos parámetros.',
                'sticky': False,
                'type': 'success',
            }
        }

    def action_abrir_proyecciones(self):
        """Acceso directo al calendario y lista de proyecciones."""
        return {
            'name': 'Proyecciones de Saca',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.proyeccion.lote',
            'view_mode': 'list,form,graph,pivot,calendar',
            'target': 'current',
        }


class AvicolaProyeccionLote(models.Model):
    _name = 'avicola.proyeccion.lote'
    _description = 'Proyección de Saca de Lotes a Matadero'
    _order = 'fecha_proyectada_saca asc, id desc'

    name = fields.Char(string='Referencia Proyección', compute='_compute_name', store=True)
    distribucion_id = fields.Many2one('avicola.distribucion', string='Lote de Distribución', ondelete='set null')
    lote_incubadora = fields.Char(string='Lote de Incubadora', required=True)
    granja_id = fields.Many2one('avicola.granja', string='Granja', required=True)
    galpon_id = fields.Many2one(
        'avicola.galpon',
        string='Galpón',
        required=True,
        domain="[('granja_id', '=', granja_id)]"
    )
    fecha_ingreso = fields.Date(string='Fecha de Entrada', required=True, default=fields.Date.today)
    cantidad_inicial = fields.Integer(string='Pollitos Ingresados', required=True)

    # Parámetros de configuración vinculados (ajustables de forma individual o global)
    config_id = fields.Many2one('avicola.proyeccion.config', string='Perfil de Parámetros', default=lambda self: self.env['avicola.proyeccion.config'].get_default_config())
    edad_objetivo_dias = fields.Integer(string='Edad Objetivo de Saca (días)', default=42, required=True)
    peso_objetivo_kg = fields.Float(string='Peso Objetivo (kg/ave)', default=2.50, digits=(10, 2), required=True)
    ganancia_diaria_gr = fields.Float(string='Ganancia Diaria (g/día)', default=59.5, digits=(10, 1), required=True)
    mortalidad_estimada_pct = fields.Float(string='Mortalidad Estimada (%)', default=3.50, digits=(10, 2), required=True)
    pollos_por_jaula = fields.Integer(string='Pollos por Jaula', default=15, required=True)
    jaulas_por_camion = fields.Integer(string='Jaulas por Camión', default=220, required=True)
    precio_estimado_kg = fields.Float(string='Precio Estimado / kg ($)', default=1.85, digits=(10, 2))

    # Métricas reales actuales en galpón
    mortalidad_acumulada = fields.Integer(
        string='Mortalidad Registrada',
        compute='_compute_mortalidad_and_stock',
        store=True,
        help='Bajas confirmadas en el galpón para este lote.'
    )
    cantidad_actual = fields.Integer(
        string='Población Actual Aves',
        compute='_compute_mortalidad_and_stock',
        store=True
    )
    mortalidad_real_pct = fields.Float(
        string='Mortalidad Real (%)',
        compute='_compute_mortalidad_and_stock',
        store=True,
        digits=(10, 2)
    )

    # Proyecciones dinámicas calculadas
    edad_actual_dias = fields.Integer(
        string='Edad Actual (días)',
        compute='_compute_proyeccion'
    )
    fecha_proyectada_saca = fields.Date(
        string='Fecha Proyectada de Saca',
        compute='_compute_proyeccion',
        store=True
    )
    dias_para_saca = fields.Integer(
        string='Días para Saca',
        compute='_compute_proyeccion'
    )
    aves_proyectadas_saca = fields.Integer(
        string='Aves Estimadas a Sacar',
        compute='_compute_proyeccion',
        store=True
    )
    peso_estimado_actual_kg = fields.Float(
        string='Peso Actual Estimado (kg)',
        compute='_compute_proyeccion',
        digits=(10, 3)
    )
    kilos_totales_proyectados = fields.Float(
        string='Kilos Totales Proyectados (kg)',
        compute='_compute_proyeccion',
        store=True,
        digits=(10, 2)
    )
    consumo_estimado_alimento_kg = fields.Float(
        string='Consumo Proyectado Alimento (kg)',
        compute='_compute_proyeccion',
        store=True,
        digits=(10, 2)
    )
    jaulas_requeridas = fields.Integer(
        string='Jaulas Requeridas',
        compute='_compute_proyeccion',
        store=True
    )
    viajes_camion_estimados = fields.Integer(
        string='Camiones Estimados',
        compute='_compute_proyeccion',
        store=True
    )
    valor_estimado_venta = fields.Float(
        string='Ingreso Proyectado ($)',
        compute='_compute_proyeccion',
        store=True,
        digits=(10, 2)
    )

    # Estado y seguimiento
    estado = fields.Selection([
        ('crecimiento', 'En Crecimiento'),
        ('proximo', 'Próximo a Sacar'),
        ('listo', 'Listo para Saca'),
        ('en_proceso', 'En Proceso de Saca'),
        ('sacado', 'Lote Sacado'),
    ], string='Estado de Saca', default='crecimiento', compute='_compute_estado', store=True)

    cliente_sugerido = fields.Char(string='Matadero / Cliente de Destino Sugerido')
    observaciones = fields.Text(string='Observaciones Operativas')

    # Seguimiento de despachos reales
    cantidad_aves_despachadas = fields.Integer(
        string='Aves Despachadas',
        compute='_compute_despachos_reales'
    )
    kilos_despachados_reales = fields.Float(
        string='Kilos Reales Despachados (kg)',
        compute='_compute_despachos_reales',
        digits=(10, 2)
    )

    @api.depends('lote_incubadora', 'galpon_id')
    def _compute_name(self):
        for rec in self:
            lote = rec.lote_incubadora or 'S-L'
            galpon = rec.galpon_id.name if rec.galpon_id else 'S-G'
            rec.name = f"PROY-{lote}-{galpon}"

    @api.depends('galpon_id', 'distribucion_id', 'cantidad_inicial')
    def _compute_mortalidad_and_stock(self):
        for rec in self:
            if rec.galpon_id:
                # Buscar mortalidad confirmada para esta granja y galpón
                mort_records = self.env['avicola.mortalidad'].search([
                    ('galpon_id', '=', rec.galpon_id.id),
                    ('estado', '=', 'confirmado'),
                    ('fecha', '>=', rec.fecha_ingreso or fields.Date.today()),
                ])
                total_mort = sum(mort_records.mapped('cantidad'))
                rec.mortalidad_acumulada = total_mort
                # Población actual: cantidad del galpón o inicial menos bajas
                rec.cantidad_actual = max(0, rec.galpon_id.cantidad_actual)
                if rec.cantidad_inicial > 0:
                    rec.mortalidad_real_pct = (float(total_mort) * 100.0) / float(rec.cantidad_inicial)
                else:
                    rec.mortalidad_real_pct = 0.0
            else:
                rec.mortalidad_acumulada = 0
                rec.cantidad_actual = rec.cantidad_inicial
                rec.mortalidad_real_pct = 0.0

    @api.depends(
        'fecha_ingreso', 'edad_objetivo_dias', 'cantidad_actual', 'cantidad_inicial',
        'mortalidad_acumulada', 'mortalidad_estimada_pct', 'peso_objetivo_kg',
        'ganancia_diaria_gr', 'pollos_por_jaula', 'jaulas_por_camion',
        'precio_estimado_kg', 'config_id.ica_estimado'
    )
    def _compute_proyeccion(self):
        today = fields.Date.today()
        for rec in self:
            fecha_in = rec.fecha_ingreso or today
            dias_vividos = max(0, (today - fecha_in).days)
            rec.edad_actual_dias = dias_vividos

            dias_meta = rec.edad_objetivo_dias or 42
            fecha_saca = fecha_in + timedelta(days=dias_meta)
            rec.fecha_proyectada_saca = fecha_saca
            rec.dias_para_saca = (fecha_saca - today).days

            # Estimación de aves vivas al momento del sacrificio
            if rec.cantidad_actual > 0:
                # Si aún faltan días, descontamos la mortalidad residual esperada
                dias_rest = max(0, rec.dias_para_saca)
                dias_totales = max(1, dias_meta)
                factor_residual = (dias_rest / dias_totales) * ((rec.mortalidad_estimada_pct or 3.5) / 100.0)
                aves_finales = int(rec.cantidad_actual * (1.0 - factor_residual))
            else:
                aves_finales = int(rec.cantidad_inicial * (1.0 - ((rec.mortalidad_estimada_pct or 3.5) / 100.0)))

            rec.aves_proyectadas_saca = max(0, aves_finales)

            # Peso estimado actual (grec.ganancia_diaria_gr * días)
            peso_act = 0.042 + ((rec.ganancia_diaria_gr or 59.5) * dias_vividos / 1000.0)
            rec.peso_estimado_actual_kg = round(min(peso_act, rec.peso_objetivo_kg or 2.50), 3)

            # Kilos totales proyectados
            kilos_totales = rec.aves_proyectadas_saca * (rec.peso_objetivo_kg or 2.50)
            rec.kilos_totales_proyectados = round(kilos_totales, 2)

            # Consumo estimado de alimento (usando ICA)
            ica = rec.config_id.ica_estimado if rec.config_id else 1.65
            rec.consumo_estimado_alimento_kg = round(kilos_totales * (ica or 1.65), 2)

            # Logística de transporte
            aves_jaula = max(1, rec.pollos_por_jaula or 15)
            jaulas_req = math.ceil(rec.aves_proyectadas_saca / aves_jaula) if rec.aves_proyectadas_saca > 0 else 0
            rec.jaulas_requeridas = jaulas_req

            jaulas_camion = max(1, rec.jaulas_por_camion or 220)
            rec.viajes_camion_estimados = math.ceil(jaulas_req / jaulas_camion) if jaulas_req > 0 else 0

            # Valor estimado de venta
            precio = rec.precio_estimado_kg or 1.85
            rec.valor_estimado_venta = round(kilos_totales * precio, 2)

    @api.depends('dias_para_saca', 'cantidad_actual', 'config_id.dias_aviso_previo')
    def _compute_estado(self):
        for rec in self:
            aviso = rec.config_id.dias_aviso_previo if rec.config_id else 7
            
            # Verificar si ya se despacharon aves de este galpón
            despachos = self.env['avicola.despacho'].search([
                ('galpon_id', '=', rec.galpon_id.id),
                ('estado', '=', 'confirmado'),
                ('fecha', '>=', rec.fecha_ingreso or fields.Date.today()),
            ])
            total_despachadas = sum(despachos.mapped('cantidad_aves'))

            if rec.cantidad_actual <= 0 and total_despachadas > 0:
                rec.estado = 'sacado'
            elif total_despachadas > 0 and rec.cantidad_actual > 0:
                rec.estado = 'en_proceso'
            elif rec.dias_para_saca <= 0:
                rec.estado = 'listo'
            elif rec.dias_para_saca <= aviso:
                rec.estado = 'proximo'
            else:
                rec.estado = 'crecimiento'

    def _compute_despachos_reales(self):
        for rec in self:
            despachos = self.env['avicola.despacho'].search([
                ('galpon_id', '=', rec.galpon_id.id),
                ('estado', '=', 'confirmado'),
                ('fecha', '>=', rec.fecha_ingreso or fields.Date.today()),
            ])
            rec.cantidad_aves_despachadas = sum(despachos.mapped('cantidad_aves'))
            rec.kilos_despachados_reales = sum(despachos.mapped('peso_neto'))

    def action_crear_despacho(self):
        """Abre un nuevo despacho pre-cargado con los datos de esta proyección de saca."""
        self.ensure_one()
        return {
            'name': f'Nuevo Despacho de Saca - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.despacho',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_granja': self.granja_id.id,
                'default_galpon_id': self.galpon_id.id,
                'default_cliente': self.cliente_sugerido or 'Matadero Central',
                'default_cantidad_aves': min(self.cantidad_actual, self.aves_proyectadas_saca) or self.cantidad_actual,
                'default_pollos_por_jaula': self.pollos_por_jaula,
                'default_cant_jaulas': self.jaulas_requeridas,
                'default_peso_neto': self.kilos_totales_proyectados,
            }
        }

    def action_recalcular(self):
        """Fuerza el refresco de las métricas de proyección."""
        self.ensure_one()
        self._compute_mortalidad_and_stock()
        self._compute_proyeccion()
        self._compute_estado()
        return True

    def action_marcar_sacado(self):
        """Permite cerrar manualmente la proyección si la saca concluyó."""
        self.ensure_one()
        self.estado = 'sacado'
