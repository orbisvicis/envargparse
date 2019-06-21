import setuptools

with open("README.rst", "r") as fh:
    long_description = fh.read()

setuptools.setup\
    ( name                              = "envargparse"
    , version                           = "1.0.0"
    , author                            = "Yclept Nemo"
    , author_email                      = "orbisvicis@gmail.com"
    , license                           = "GPLv3+"
    , url                               = "https://github.com/orbisvicis/envargparse"
    , description                       = "Argparse with environment variables"
    , long_description                  = long_description
    , long_description_content_type     = "text/x-rst"
    , classifiers                       =\
        [ "Development Status :: 5 - Production/Stable"
        , "Intended Audience :: Developers"
        , "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)"
        , "Operating System :: OS Independent"
        , "Programming Language :: Python :: 3 :: Only"
        , "Topic :: Software Development :: Libraries"
        ]
    , python_requires                   = ">= 3.7"
    , install_requires                  = [ "decorator" ]
    , py_modules                        = [ "envargparse" ]
    )
