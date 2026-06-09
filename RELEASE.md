# Cómo publicar una nueva versión

Son dos pasos: GitHub Release automático y AUR manual.

## 1. GitHub Release

1. Etiquetá la versión:

```bash
git tag v1.0.0
git push github master v1.0.0
```

2. GitHub Actions compila `fila.bin`, arma `fila-1.0.0-linux-x86_64.tar.gz` y publica el release.

## 2. AUR (`fila-bin`)

Cuando el release ya está publicado:

```bash
make aur-update
```

Or:

```bash
just aur-update 1.0.0
```

El script:

1. Toma la última release publicada o la versión que le pases.
2. Descarga el tarball.
3. Calcula el SHA256.
4. Clona el repo de AUR.
5. Actualiza `PKGBUILD` y `.SRCINFO`.
6. Hace commit y push al AUR.

## Resumen

```bash
git tag v1.0.0
git push github master v1.0.0
make aur-update
```

O equivalente:

```bash
just aur-update 1.0.0
```
