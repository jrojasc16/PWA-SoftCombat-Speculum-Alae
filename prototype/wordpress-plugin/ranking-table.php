<?php
/**
 * Plugin Name: Speculum-Alae — Ranking Table
 * Plugin URI:  https://github.com/jrojasc16/PWA-SoftCombat-Speculum-Alae
 * Description: Shortcode [ranking_table] que publica el ranking público de la comunidad Speculum-Alae consumiendo el endpoint GET /api/ranking del backend Flask (HTTP API de WordPress).
 * Version:     1.0.0
 * Author:      Equipo Speculum-Alae
 * License:     GPL-2.0-or-later
 * License URI: https://www.gnu.org/licenses/gpl-2.0.html
 * Text Domain: speculum-alae
 * Requires at least: 5.5
 * Requires PHP: 7.4
 *
 * Este plugin no toca la base de datos de WordPress: solo consulta el
 * endpoint público del prototipo Flask (RNF002/RF12) y pinta una tabla.
 * En producción el backend debe exponerse por HTTPS (RNF001).
 */

defined( 'ABSPATH' ) || exit;

/** Versión del plugin (identifica el archivo en los ajustes de WordPress). */
define( 'SA_RANKING_VERSION', '1.0.0' );

/** URL base por defecto del backend del prototipo (se cambia en Ajustes). */
define( 'SA_RANKING_API_DEFECTO', 'http://127.0.0.1:5000' );

/** Caché por defecto del shortcode: ~5 minutos (segundos). */
define( 'SA_RANKING_TTL_DEFECTO', 300 );

/** Caché máxima admisible: 24 horas (segundos). */
define( 'SA_RANKING_TTL_MAXIMO', 86400 );

/** Segundos de espera máxima por petición al backend. */
define( 'SA_RANKING_TIMEOUT', 5 );

/** Transient con el HTML vigente: caduca a los TTL configurados (~5 min). */
define( 'SA_RANKING_TRANSIENTE', 'sa_ranking_cache' );

/**
 * Transient de respaldo: conserva el último HTML **sin** caducidad para
 * poder servir una copia desactualizada si el backend deja de responder.
 */
define( 'SA_RANKING_TRANSIENTE_RESPALDO', 'sa_ranking_respaldo' );

/**
 * TTL efectivo del caché (segundos).
 *
 * Lee el ajuste ``sa_ranking_ttl`` (por defecto ~5 minutos, RNF004/RF12)
 * y lo acota al rango 0..24 h. Un TTL de 0 desactiva el caché: el shortcode
 * consulta la API en cada vista y no guarda copias.
 *
 * @return int Segundos (0..SA_RANKING_TTL_MAXIMO).
 */
function sa_ranking_ttl() {
	$ttl = (int) get_option( 'sa_ranking_ttl', SA_RANKING_TTL_DEFECTO );

	if ( $ttl < 0 ) {
		return 0;
	}
	if ( $ttl > SA_RANKING_TTL_MAXIMO ) {
		return SA_RANKING_TTL_MAXIMO;
	}

	return $ttl;
}

/**
 * Clave interna del caché para una combinación de comunidad y página.
 *
 * El transient guarda un array con varias entradas (una por shortcode con
 * atributos distintos), así que hace falta distinguirlas dentro.
 *
 * @param int $comunidad  Comunidad.
 * @param int $por_pagina Tamaño de página.
 * @return string Clave estable, p. ej. "1x50".
 */
function sa_ranking_clave( $comunidad, $por_pagina ) {
	return $comunidad . 'x' . $por_pagina;
}

/**
 * Devuelve el HTML cacheado si el caché sigue vivo.
 *
 * @param string $clave Clave interna (ver sa_ranking_clave).
 * @return string|null HTML o null si no hay caché vigente.
 */
function sa_ranking_leer_cache( $clave ) {
	// TTL 0 = caché desactivado desde los ajustes.
	if ( sa_ranking_ttl() <= 0 ) {
		return null;
	}

	$cache = get_transient( SA_RANKING_TRANSIENTE );

	if ( ! is_array( $cache ) || ! isset( $cache[ $clave ] ) || ! is_string( $cache[ $clave ] ) ) {
		return null;
	}

	return $cache[ $clave ];
}

/**
 * Devuelve el último HTML conocido, **aunque el TTL haya caducado**.
 *
 * @param string $clave Clave interna.
 * @return string|null HTML de respaldo o null si nunca hubo uno.
 */
function sa_ranking_leer_respaldo( $clave ) {
	$respaldo = get_transient( SA_RANKING_TRANSIENTE_RESPALDO );

	if ( ! is_array( $respaldo ) || ! isset( $respaldo[ $clave ] ) || ! is_string( $respaldo[ $clave ] ) ) {
		return null;
	}

	return $respaldo[ $clave ];
}

/**
 * Guarda el HTML en el caché vigente y en el respaldo sin caducidad.
 *
 * Con TTL 0 no se guarda nada (ajuste «sin caché»): ni la tabla vigente ni
 * el respaldo, de modo que la opción significa «consultar siempre».
 *
 * @param string $clave Clave interna.
 * @param string $html  Tabla ya construida y escapada.
 */
function sa_ranking_escribir_cache( $clave, $html ) {
	if ( sa_ranking_ttl() <= 0 ) {
		return;
	}

	$cache = get_transient( SA_RANKING_TRANSIENTE );
	$cache = is_array( $cache ) ? $cache : array();
	$cache[ $clave ] = $html;
	set_transient( SA_RANKING_TRANSIENTE, $cache, sa_ranking_ttl() );

	$respaldo = get_transient( SA_RANKING_TRANSIENTE_RESPALDO );
	$respaldo = is_array( $respaldo ) ? $respaldo : array();
	$respaldo[ $clave ] = $html;
	// TTL 0 en WordPress = sin caducidad: es la copia de última instancia.
	set_transient( SA_RANKING_TRANSIENTE_RESPALDO, $respaldo, 0 );
}

/**
 * Borra ambos transients (caché vigente y respaldo).
 *
 * Idempotente: se usa al cambiar los ajustes para no servir datos de una
 * API que ya no es la configurada.
 */
function sa_ranking_limpiar_cache() {
	delete_transient( SA_RANKING_TRANSIENTE );
	delete_transient( SA_RANKING_TRANSIENTE_RESPALDO );
}

/**
 * URL completa del endpoint público de ranking.
 *
 * Une la URL base guardada en los ajustes (``sa_ranking_api_base``, por
 * defecto la del prototipo local) con la ruta del endpoint y añade los
 * parámetros que el backend conoce (``community_id`` para el aislamiento
 * por comunidad RNF006 y ``per_page`` para acotar la respuesta).
 *
 * @param int $comunidad  Comunidad (>= 1).
 * @param int $por_pagina Tamaño de página (1..100).
 * @return string URL lista para wp_remote_get().
 */
function sa_ranking_url_api( $comunidad, $por_pagina ) {
	$base = get_option( 'sa_ranking_api_base', SA_RANKING_API_DEFECTO );
	$base = is_string( $base ) && '' !== trim( $base ) ? trim( $base ) : SA_RANKING_API_DEFECTO;
	$url  = rtrim( $base, '/' ) . '/api/ranking';

	return add_query_arg(
		array(
			'community_id' => $comunidad,
			'per_page'     => $por_pagina,
		),
		$url
	);
}

/**
 * Consulta el endpoint público y devuelve el payload decodificado.
 *
 * Se descarta cualquier respuesta que no sea un 200 con un JSON que traiga
 * ``items``: así un backend caído o un HTML de error nunca llega a la tabla.
 *
 * @param int $comunidad  Comunidad (RNF006).
 * @param int $por_pagina Tamaño de página (1..100).
 * @return array|null Payload del endpoint o null si no se pudo consultar.
 */
function sa_ranking_consultar_api( $comunidad, $por_pagina ) {
	$respuesta = wp_remote_get(
		sa_ranking_url_api( $comunidad, $por_pagina ),
		array(
			'timeout'     => SA_RANKING_TIMEOUT,
			'sslverify'   => true,
			'redirection' => 3,
			'headers'     => array( 'Accept' => 'application/json' ),
		)
	);

	if ( is_wp_error( $respuesta ) ) {
		return null;
	}

	if ( 200 !== (int) wp_remote_retrieve_response_code( $respuesta ) ) {
		return null;
	}

	$datos = json_decode( wp_remote_retrieve_body( $respuesta ), true );

	if ( ! is_array( $datos ) || ! isset( $datos['items'] ) || ! is_array( $datos['items'] ) ) {
		return null;
	}

	return $datos;
}

/**
 * Pinta la tabla HTML a partir del payload del endpoint.
 *
 * Reproduce la vista pública ``/ranking`` del prototipo: mismas columnas en
 * el mismo orden (Pos., Jugador, Puntos, Combates), mismo formato de puntos
 * con un decimal y el mismo mensaje vacío. Toda la salida se escapa con
 * ``esc_html`` para que un nombre de jugador no pueda inyectar HTML.
 *
 * @param array $datos Payload con ``items`` y ``total``.
 * @return string HTML de la tabla (o mensaje vacío).
 */
function sa_ranking_construir_tabla( $datos ) {
	$items = $datos['items'];
	$total = isset( $datos['total'] ) ? (int) $datos['total'] : count( $items );

	if ( empty( $items ) ) {
		return '<p class="sa-ranking-vacio">'
			. esc_html__(
				'Todavía no hay combates confirmados: el ranking aparecerá con la primera partida cerrada.',
				'speculum-alae'
			)
			. '</p>';
	}

	$pie = sprintf(
		/* translators: %d: número de jugadores con índice. */
		_n( '%d jugador con índice', '%d jugadores con índice', $total, 'speculum-alae' ),
		$total
	);

	$html  = '<div class="sa-ranking-envoltura">';
	$html .= '<table class="sa-ranking-tabla">';
	$html .= '<caption class="sa-ranking-pie-tabla">' . esc_html( $pie ) . '</caption>';
	$html .= '<thead><tr>'
		. '<th scope="col">' . esc_html__( 'Pos.', 'speculum-alae' ) . '</th>'
		. '<th scope="col">' . esc_html__( 'Jugador', 'speculum-alae' ) . '</th>'
		. '<th scope="col">' . esc_html__( 'Puntos', 'speculum-alae' ) . '</th>'
		. '<th scope="col">' . esc_html__( 'Combates', 'speculum-alae' ) . '</th>'
		. '</tr></thead><tbody>';

	foreach ( $items as $item ) {
		$posicion = isset( $item['position'] ) ? (int) $item['position'] : 0;
		$nombre   = isset( $item['name'] ) ? (string) $item['name'] : '';
		$puntos   = isset( $item['points'] ) ? (float) $item['points'] : 0.0;
		$combates = isset( $item['matches_played'] ) ? (int) $item['matches_played'] : 0;

		$html .= '<tr>'
			. '<td class="sa-ranking-pos">' . esc_html( (string) $posicion ) . '</td>'
			. '<td class="sa-ranking-jugador">' . esc_html( $nombre ) . '</td>'
			. '<td class="sa-ranking-puntos">' . esc_html( number_format( $puntos, 1, '.', '' ) ) . '</td>'
			. '<td class="sa-ranking-combates">' . esc_html( (string) $combates ) . '</td>'
			. '</tr>';
	}

	$html .= '</tbody></table></div>';

	return $html;
}

/**
 * Shortcode ``[ranking_table]``.
 *
 * Flujo (secuencia 04_wordpress_ranking):
 *
 * 1. caché vivo en Transients → se sirve sin tocar el backend;
 * 2. consulta ``GET /api/ranking`` → construye la tabla y la cachea;
 * 3. backend caído → sirve el **respaldo** (última copia, avisando de que
 *    está desactualizada);
 * 4. sin datos previos → mensaje degradado.
 *
 * Atributos opcionales:
 *
 * - ``community_id`` — comunidad a mostrar (por defecto 1, RNF006).
 * - ``per_page``     — nº de filas (por defecto 50, máximo 100, igual que el
 *                      endpoint para no pedir más de lo permitido).
 *
 * @param array $atts Atributos del shortcode.
 * @return string HTML del ranking (tabla o mensaje).
 */
function sa_ranking_shortcode( $atts ) {
	$atts = shortcode_atts(
		array(
			'community_id' => 1,
			'per_page'     => 50,
		),
		$atts,
		'ranking_table'
	);

	$comunidad  = max( 1, absint( $atts['community_id'] ) );
	$por_pagina = min( 100, max( 1, absint( $atts['per_page'] ) ) );
	$clave      = sa_ranking_clave( $comunidad, $por_pagina );

	// 1) Caché vigente: respuesta inmediata sin consultar el backend.
	$cacheado = sa_ranking_leer_cache( $clave );
	if ( null !== $cacheado ) {
		return $cacheado;
	}

	// 2) Caché frío: se consulta el endpoint público.
	$datos = sa_ranking_consultar_api( $comunidad, $por_pagina );
	if ( null !== $datos ) {
		$html = sa_ranking_construir_tabla( $datos );
		sa_ranking_escribir_cache( $clave, $html );

		return $html;
	}

	// 3) Backend caído: última tabla conocida, marcada como desactualizada.
	$respaldo = sa_ranking_leer_respaldo( $clave );
	if ( null !== $respaldo ) {
		return '<p class="sa-ranking-desactualizado" role="status">'
			. esc_html__(
				'No se pudo actualizar el ranking: se muestra la última copia guardada.',
				'speculum-alae'
			)
			. '</p>'
			. $respaldo;
	}

	// 4) Nunca hubo datos: mensaje degradado.
	return '<p class="sa-ranking-agotado" role="status">'
		. esc_html__(
			'El ranking no está disponible en este momento: no se pudo contactar con el servidor. Inténtalo de nuevo en unos minutos.',
			'speculum-alae'
		)
		. '</p>';
}

add_shortcode( 'ranking_table', 'sa_ranking_shortcode' );

// ---------------------------------------------------------------------------
// Ajustes del plugin (tarea 11.3): URL base de la API y TTL del caché.
// ---------------------------------------------------------------------------

add_action( 'admin_menu', 'sa_ranking_registrar_pagina_ajustes' );
add_action( 'admin_init', 'sa_ranking_registrar_ajustes' );
// Al cambiar la configuración se vacía el caché para no servir datos de una
// API que ya no es la configurada.
add_action( 'update_option_sa_ranking_api_base', 'sa_ranking_limpiar_cache' );
add_action( 'update_option_sa_ranking_ttl', 'sa_ranking_limpiar_cache' );

/**
 * Crea la página de ajustes dentro de Ajustes → Ranking SA.
 */
function sa_ranking_registrar_pagina_ajustes() {
	add_options_page(
		__( 'Ranking Speculum-Alae', 'speculum-alae' ),
		__( 'Ranking SA', 'speculum-alae' ),
		'manage_options',
		'sa-ranking-table',
		'sa_ranking_pintar_ajustes'
	);
}

/**
 * Registra las dos opciones con la Settings API de WordPress.
 */
function sa_ranking_registrar_ajustes() {
	register_setting(
		'sa_ranking_grupo',
		'sa_ranking_api_base',
		array(
			'type'              => 'string',
			'sanitize_callback' => 'sa_ranking_sanitizar_url',
			'default'           => SA_RANKING_API_DEFECTO,
		)
	);

	register_setting(
		'sa_ranking_grupo',
		'sa_ranking_ttl',
		array(
			'type'              => 'integer',
			'sanitize_callback' => 'sa_ranking_sanitizar_ttl',
			'default'           => SA_RANKING_TTL_DEFECTO,
		)
	);

	add_settings_section(
		'sa_ranking_seccion',
		__( 'Conexión con el backend', 'speculum-alae' ),
		'__return_false',
		'sa-ranking-table'
	);

	add_settings_field(
		'sa_ranking_api_base',
		__( 'URL base de la API', 'speculum-alae' ),
		'sa_ranking_campo_url',
		'sa-ranking-table',
		'sa_ranking_seccion'
	);

	add_settings_field(
		'sa_ranking_ttl',
		__( 'Caché del ranking (segundos)', 'speculum-alae' ),
		'sa_ranking_campo_ttl',
		'sa-ranking-table',
		'sa_ranking_seccion'
	);
}

/**
 * Sanea la URL base: solo http/https, sin barra final y con valor de defecto.
 *
 * @param mixed $valor Valor crudo del formulario.
 * @return string URL válida.
 */
function sa_ranking_sanitizar_url( $valor ) {
	$valor = is_string( $valor ) ? trim( $valor ) : '';
	$valor = esc_url_raw( $valor, array( 'http', 'https' ) );

	if ( '' === $valor ) {
		return SA_RANKING_API_DEFECTO;
	}

	return untrailingslashit( $valor );
}

/**
 * Sanea el TTL: entero entre 0 (sin caché) y 24 horas.
 *
 * @param mixed $valor Valor crudo del formulario.
 * @return int Segundos acotados.
 */
function sa_ranking_sanitizar_ttl( $valor ) {
	$valor = (int) $valor;

	if ( $valor < 0 ) {
		return 0;
	}
	if ( $valor > SA_RANKING_TTL_MAXIMO ) {
		return SA_RANKING_TTL_MAXIMO;
	}

	return $valor;
}

/**
 * Campo de formulario: URL base de la API.
 */
function sa_ranking_campo_url() {
	$url = get_option( 'sa_ranking_api_base', SA_RANKING_API_DEFECTO );
	$url = is_string( $url ) && '' !== trim( $url ) ? trim( $url ) : SA_RANKING_API_DEFECTO;

	// Solo se admite http/https (el resto → valor por defecto).
	$esquema = wp_parse_url( $url, PHP_URL_SCHEME );
	if ( ! in_array( $esquema, array( 'http', 'https' ), true ) ) {
		$url = SA_RANKING_API_DEFECTO;
	}

	printf(
		'<input type="url" id="sa_ranking_api_base" name="sa_ranking_api_base" value="%s" class="regular-text" placeholder="%s" />',
		esc_attr( $url ),
		esc_attr( SA_RANKING_API_DEFECTO )
	);

	printf(
		'<p class="description">%s</p>',
		esc_html__(
			'Ej.: https://speculum-alae.example.com — el plugin añade /api/ranking. En producción el backend debe responder por HTTPS.',
			'speculum-alae'
		)
	);
}

/**
 * Campo de formulario: TTL del caché.
 */
function sa_ranking_campo_ttl() {
	$ttl = sa_ranking_ttl();

	printf(
		'<input type="number" id="sa_ranking_ttl" name="sa_ranking_ttl" value="%d" min="0" max="%d" step="1" class="small-text" />',
		$ttl,
		SA_RANKING_TTL_MAXIMO
	);

	printf(
		'<p class="description">%s</p>',
		esc_html__(
			'Segundos antes de volver a consultar la API (300 = 5 minutos, el valor por defecto). 0 desactiva el caché: siempre se consulta y no se guarda copia de respaldo.',
			'speculum-alae'
		)
	);
}

/**
 * Pinta la página de ajustes (solo para administradores).
 */
function sa_ranking_pintar_ajustes() {
	if ( ! current_user_can( 'manage_options' ) ) {
		return;
	}
	?>
	<div class="wrap">
		<h1><?php echo esc_html( get_admin_page_title() ); ?></h1>
		<form action="options.php" method="post">
			<?php
			settings_fields( 'sa_ranking_grupo' );
			do_settings_sections( 'sa-ranking-table' );
			submit_button();
			?>
		</form>
	</div>
	<?php
}
