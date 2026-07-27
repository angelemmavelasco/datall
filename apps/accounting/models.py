from datetime import date
from dateutil.relativedelta import relativedelta
from django.db import models

class TaxRegimeChoices(models.TextChoices):
    GENERAL_PERSONAS_MORALES = '601', '601 General de Ley Personas Morales'
    PERSONAS_MORALES_FINES_NO_LUCRATIVOS = '603', '603 Personas Morales con Fines no Lucrativos'
    SUELDOS_SALARIOS = '605', '605 Sueldos y Salarios e Ingresos Asimilados a Salarios'
    ARRENDAMIENTO = '606', '606 Arrendamiento'
    ENAJENACION_BIENES = '607', '607 Régimen de Enajenación o Adquisición de Bienes'
    DEMAS_INGRESOS = '608', '608 Demás ingresos'
    RESIDENTES_EXTRANJERO = '610', '610 Residentes en el Extranjero sin Establecimiento Permanente en México'
    DIVIDENDOS = '611', '611 Ingresos por Dividendos (socios y accionistas)'
    ACTIVIDADES_EMPRESARIALES_PROFESIONALES = '612', '612 Personas Físicas con Actividades Empresariales y Profesionales'
    INTERESES = '614', '614 Ingresos por intereses'
    PREMIOS = '615', '615 Régimen de los ingresos por obtención de premios'
    SIN_OBLIGACIONES_FISCALES = '616', '616 Sin obligaciones fiscales'
    SOCIEDADES_COOPERATIVAS = '620', '620 Sociedades Cooperativas de Producción que optan por diferir sus ingresos'
    INCORPORACION_FISCAL = '621', '621 Incorporación Fiscal (RIF)'
    AGRAPES = '622', '622 Actividades Agrícolas, Ganaderas, Silvícolas y Pesqueras (AGAPES)'
    GRUPOS_SOCIEDADES = '623', '623 Opcional para Grupos de Sociedades'
    COORDINADOS = '624', '624 Coordinados'
    PLATAFORMAS_TECNOLOGICAS = '625', '625 Actividades Empresariales con ingresos a través de Plataformas Tecnológicas'
    RESICO = '626', '626 Régimen Simplificado de Confianza (RESICO)'

class PaymentFormChoices(models.TextChoices):
    _01 = '01', '01 Efectivo'
    _02 = '02', '02 Cheque nominativo'
    _03 = '03', '03 Transferencia electrónica de fondos'
    _04 = '04', '04 Tarjeta de crédito'
    _05 = '05', '05 Monedero electrónico'
    _06 = '06', '06 Dinero electrónico'
    _08 = '08', '08 Vales de despensa'
    _12 = '12', '12 Dación en pago'
    _13 = '13', '13 Pago por subrogación'
    _14 = '14', '14 Pago por consignación'
    _15 = '15', '15 Condonación'
    _17 = '17', '17 Compensación'
    _23 = '23', '23 Novación'
    _24 = '24', '24 Confusión'
    _25 = '25', '25 Remisión de deuda'
    _26 = '26', '26 Prescripción o caducidad'
    _27 = '27', '27 A satisfacción del acreedor'
    _28 = '28', '28 Tarjeta de débito'
    _29 = '29', '29 Tarjeta de servicios'
    _30 = '30', '30 Aplicación de anticipos'
    _31 = '31', '31 Intermediario pagos'
    _99 = '99', '99 Por definir'

class PeriodicityChoices(models.TextChoices):
    DAILY = '1d', '1 día'
    WEEKLY = '1w', '1 semana'
    FORTNIGHTLY = '2w', '2 semanas'
    MONTHLY = '1m', '1 mes'
    BIMONTHLY = '2m', '2 meses'
    QUARTERLY = '3m', '3 meses'
    FOUR_MONTHS = '4m', '4 meses'
    FIVE_MONTHS = '5m', '5 meses'
    SEMIANNUAL = '6m', '6 meses'
    SEVEN_MONTHS = '7m', '7 meses'
    EIGHT_MONTHS = '8m', '8 meses'
    NINE_MONTHS = '9m', '9 meses'
    TEN_MONTHS = '10m', '10 meses'
    ELEVEN_MONTHS = '11m', '11 meses'
    ANNUAL = '1y', '1 año'

    def get_relativedelta(self) -> relativedelta:
        '''
        calculates the relativedelta based on the numeric and key ref value, example : 1d -> 1 day, 11m -> 11 months, 1y -> 1 year
        '''
        val = str(self.value)
        amount = int(val[:-1])
        unit = val[-1].lower()   

        unit_mapping = {
            'd': 'days',
            'w': 'weeks',
            'm': 'months',
            'y': 'years',
        }

        kwargs = {unit_mapping.get(unit, 'months'): amount}
        return relativedelta(**kwargs)

    def get_next_date(self, from_date: date) -> date:
        '''
        calculates the next date from a provided date
        '''
        return from_date + self.get_relativedelta()
