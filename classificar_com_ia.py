from openai import OpenAI
import json, os

client = OpenAI(api_key="SUA_API_KEY")

def classificar_com_ia(texto):
    try:
        prompt = f"""
        Analise o documento abaixo e retorne APENAS um JSON válido no formato:

        {{
          "categoria": "Financeiro | Estudos | Trabalho | Pessoal",
          "subcategoria": "string curta",
          "confianca": número de 0 a 100
        }}

        Documento:
        {texto[:3000]}
        """

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )

        resposta = response.choices[0].message.content.strip()

        return json.loads(resposta)

    except:
        return {
            "categoria": "Revisar",
            "subcategoria": "",
            "confianca": 0
        }
    
def decidir_destino(resposta):
    if resposta["confianca"] < 70:
        return "Revisar"

    categoria = resposta["categoria"]
    subcategoria = resposta["subcategoria"]

    return os.path.join(categoria, subcategoria)