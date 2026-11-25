shader_type spatial;
render_mode cull_disabled, depth_draw_always;
// Eau : vagues par bruit animé, couleur selon la profondeur, reflets de Fresnel.

uniform vec3 shallow : source_color = vec3(0.25, 0.55, 0.6);
uniform vec3 deep : source_color = vec3(0.04, 0.17, 0.3);
uniform sampler2D wave_a : hint_normal, filter_linear_mipmap, repeat_enable;
uniform sampler2D wave_b : hint_normal, filter_linear_mipmap, repeat_enable;
uniform sampler2D DEPTH_TEXTURE : hint_depth_texture, filter_linear_mipmap;

varying vec3 wpos;

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	VERTEX.y += sin(wpos.x * 0.35 + TIME * 1.1) * 0.03 + cos(wpos.z * 0.3 + TIME * 0.9) * 0.03;
}

void fragment() {
	vec2 uv1 = wpos.xz * 0.05 + vec2(TIME * 0.012, TIME * 0.008);
	vec2 uv2 = wpos.xz * 0.08 - vec2(TIME * 0.01, -TIME * 0.015);
	vec3 n = mix(texture(wave_a, uv1).rgb, texture(wave_b, uv2).rgb, 0.5);
	NORMAL_MAP = n;
	NORMAL_MAP_DEPTH = 0.6;
	float depth = texture(DEPTH_TEXTURE, SCREEN_UV).r;
	vec4 world = INV_PROJECTION_MATRIX * vec4(SCREEN_UV * 2.0 - 1.0, depth, 1.0);
	world.xyz /= world.w;
	float dist = clamp((-world.z - (-VERTEX.z)) * 0.35, 0.0, 1.0);
	float fres = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), 4.0);
	vec3 col = mix(shallow, deep, dist);
	ALBEDO = col;
	ROUGHNESS = 0.05;
	METALLIC = 0.0;
	SPECULAR = 0.6 + fres * 0.4;
	ALPHA = clamp(0.55 + dist * 0.45 + fres * 0.2, 0.0, 0.97);
}
