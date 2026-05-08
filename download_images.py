import requests

for i in range(83):
    url = f"https://www.medellin.gov.co/SIMM/camaras-cctv/imagen{i}.jpg"
    response = requests.get(url)

    if response.status_code == 200:
        #guardar el archivo
        with open(f"images/imagen{i}.jpg", "wb") as f:
            f.write(response.content) 
        print(f"Imagen {i} descargada exitosamente.")
    else:
        print(f"Error al descargar la imagen {i}: Código de estado {response.status_code}.")