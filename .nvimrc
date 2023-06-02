
au BufWritePost schemander.py ! black schemander.py
au BufWritePost schemander.py cexpr system('mypy --strict -m schemander')
