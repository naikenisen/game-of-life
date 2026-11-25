shader_type spatial;
// Terrain : mélange de 6 matériaux (poids par sommet), projection triplanaire
// pour la roche sur les pentes, macro-variation pour casser la répétition.

uniform sampler2D grass_a : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D grass_n : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D forest_a : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D forest_n : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D sand_a : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D sand_n : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D soil_a : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D soil_n : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D rock_a : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D rock_n : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D gravel_a : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D gravel_n : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D macro_noise : filter_linear_mipmap, repeat_enable;
uniform float tiling = 0.22;
uniform vec3 grass_tint = vec3(0.78, 1.0, 0.62);

varying vec3 wpos;
varying vec3 wnorm;
varying vec4 w1;
varying vec4 w2;

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	wnorm = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
	w1 = COLOR;
	w2 = CUSTOM0;
}

vec3 tri(sampler2D t, vec3 p, vec3 bw, float s) {
	return texture(t, p.zy * s).rgb * bw.x + texture(t, p.xz * s).rgb * bw.y + texture(t, p.xy * s).rgb * bw.z;
}

void fragment() {
	vec2 uv = wpos.xz * tiling;
	float slope = 1.0 - clamp(wnorm.y, 0.0, 1.0);
	vec4 a = w1;
	vec4 b = w2;
	// les pentes raides deviennent rocheuses
	float steep = smoothstep(0.35, 0.6, slope);
	a *= (1.0 - steep);
	b.x = max(b.x, steep);
	float sum = a.x + a.y + a.z + a.w + b.x + b.y + 0.0001;
	a /= sum;
	b /= sum;
	float macro = texture(macro_noise, wpos.xz * 0.012).r;
	vec3 bw = pow(abs(wnorm), vec3(4.0));
	bw /= (bw.x + bw.y + bw.z);
	// on ne lit que les couches réellement présentes (gros gain sur les GPU modestes)
	vec3 col = vec3(0.0);
	vec3 nm = vec3(0.0);
	if (a.x > 0.01) { col += texture(grass_a, uv).rgb * grass_tint * mix(0.8, 1.15, macro) * a.x; nm += texture(grass_n, uv).rgb * a.x; }
	if (a.y > 0.01) { col += texture(forest_a, uv).rgb * a.y; nm += texture(forest_n, uv).rgb * a.y; }
	if (a.z > 0.01) { col += texture(sand_a, uv * 0.8).rgb * a.z; nm += texture(sand_n, uv * 0.8).rgb * a.z; }
	if (a.w > 0.01) { col += texture(soil_a, uv).rgb * a.w; nm += texture(soil_n, uv).rgb * a.w; }
	if (b.x > 0.01) {
		col += (steep > 0.05 ? tri(rock_a, wpos, bw, tiling * 0.6) : texture(rock_a, wpos.xz * tiling * 0.6).rgb) * b.x;
		nm += texture(rock_n, wpos.xz * tiling * 0.6).rgb * b.x;
	}
	if (b.y > 0.01) { col += texture(gravel_a, uv).rgb * b.y; nm += texture(gravel_n, uv).rgb * b.y; }
	nm += vec3(0.5, 0.5, 1.0) * max(0.0, 1.0 - (a.x + a.y + a.z + a.w + b.x + b.y));
	ALBEDO = col * mix(0.9, 1.05, macro);
	NORMAL_MAP = nm;
	NORMAL_MAP_DEPTH = 0.8;
	ROUGHNESS = 0.92 - 0.1 * a.z;
	SPECULAR = 0.3;
}
