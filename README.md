# Raster Analysis Application

## Overview

The Raster Analysis Application is a powerful tool designed for processing and analyzing raster data, particularly focused on remote sensing applications. This application allows users to visualize satellite imagery, calculate various vegetation indices such as NDVI, and access data from Google Earth Engine and Sentinel satellites.

## Features

- **Image Zooming**: Users can zoom in and out on satellite images for detailed analysis.
  
- **NDVI Calculation**: The application computes the Normalized Difference Vegetation Index (NDVI) from loaded raster data channels, enabling users to assess vegetation health and coverage.
  
- **Google Earth Engine Integration**: Users can authorize and connect to Google Earth Engine for advanced geospatial analysis and access to a vast repository of earth observation data.
  
- **Sentinel Data Download**: Users can download Sentinel-2 satellite imagery based on specified criteria, including geographical area, date range, and cloud cover percentage.

  ## Usage

- **Loading Images**: Users can load raster images into the application for analysis.
- **Calculating NDVI**: After loading the necessary bands (red and NIR), users can compute the NDVI. The application ensures that all required channels are loaded before processing.
- **Authorizing Google Earth Engine**: Users must provide their credentials to access Google Earth Engine services.
- **Downloading Sentinel Images**: Users can enter their credentials and select desired Sentinel products for download.

## Code Example

Here’s a snippet from the code that demonstrates the NDVI calculation:

```python
def calculateNDVI(self):
    if not self.rasterData:
        return

    red = self.rasterData.get(0)
    nir = self.rasterData.get(3)

    if red is None or nir is None:
        QMessageBox.warning(self, "Error", "Please load all required channels.")
        return

    ndvi = (nir - red) / (nir + red + 1e-8)  # Adding 1e-8 to avoid division by zero
    ...
```


## Contributing
Contributions are welcome! Please feel free to submit issues and pull requests to help improve the application.

## License
This project is licensed under the MIT License - see the LICENSE file for details.

