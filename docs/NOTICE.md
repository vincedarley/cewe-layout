NOTICE
======

This project (cewe-layout / QLayout) includes and adapts ideas and algorithms from the following sources. We provide this NOTICE to document authorship and attribution.

1) Algorithm Implementations Based on Published Research

- **Fan Layout Algorithm**: Based on "Photo layout with a fast evaluation method and genetic algorithm" by Jian Fan (2012 IEEE ICMEW). Implementation in `cewe_layout/algorithms/fan_layout.py` follows the published algorithm design.

- **Collage Generator Algorithm**: Based on "Very fast generation of content-preserved photo collage under canvas size constraint" by Wu, Zhipeng, and Kiyoharu Aizawa (Multimedia Tools and Applications, 2016). The implementation in `cewe_layout/algorithms/collage_generator.py` adapts concepts from the reference implementation by n-gao (https://github.com/n-gao/collage-generator), which is MIT licensed.

2) Third-Party Dependencies

- See `requirements.txt` for all Python dependencies and their respective licenses.
- Notable dependencies include: lxml, opencv-python, numpy, pillow, and tkinter (Python standard library).

3) Acknowledgments

This project was partially inspired by the cewe2pdf project (https://github.com/bash0/cewe2pdf) (which is used for turning CEWE files into complete detailed PDF files). However the use-case is very different, and no code was directly copied.

If you believe an attribution is missing or incorrect, please open an issue or submit a pull request to update this NOTICE.
