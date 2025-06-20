import time
import requests
import plotly.graph_objects as go
from io import BytesIO
from datetime import datetime

# Configurações
DEXSCREENER_TOKEN_PROFILES_API = "https://api.dexscreener.com/token-profiles/latest/v1"
DEXSCREENER_TOKEN_PAIRS_API = "https://api.dexscreener.com/token-pairs/v1/solana/"
TELEGRAM_BOT_TOKEN = "7315720854:AAFhL9UpORYdUNvApljzx--4jagMiBujo2w"
TELEGRAM_CHAT_ID = "-1002177087466"
CHECK_INTERVAL = 300  # 5 minutos para verificar novos tokens
LIQUIDITY_THRESHOLD = 5000  # Liquidez mínima em USD

# Listas para controle
known_tokens = []  # Tokens já processados

def log(message, level="INFO"):
    """Exibe uma mensagem de log formatada no console."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level}] {message}")

def fetch_token_profiles():
    """Busca os perfis mais recentes de tokens."""
    try:
        log("Iniciando busca por perfis de tokens...", "DEBUG")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(DEXSCREENER_TOKEN_PROFILES_API, headers=headers, timeout=15)
        log(f"Resposta da API - Status: {response.status_code}", "DEBUG")
        
        response.raise_for_status()
        data = response.json()
        
        if not isinstance(data, list):
            log("Formato inesperado dos dados da API - esperada lista", "ERROR")
            return []
            
        log(f"Total de tokens recebidos: {len(data)}", "DEBUG")
        
        # Filtra apenas tokens da Solana
        solana_tokens = [token for token in data if isinstance(token, dict) and token.get("chainId") == "solana"]
        log(f"Tokens da Solana encontrados: {len(solana_tokens)}", "INFO")
        
        return solana_tokens
    except requests.exceptions.RequestException as e:
        log(f"Erro na requisição: {str(e)}", "ERROR")
        return []
    except ValueError as e:
        log(f"Erro ao decodificar JSON: {str(e)}", "ERROR")
        return []
    except Exception as e:
        log(f"Erro inesperado: {str(e)}", "ERROR")
        return []

def fetch_token_details(token_address):
    """Busca detalhes de um token específico com tratamento robusto de erros."""
    try:
        log(f"Buscando detalhes para o token: {token_address}", "DEBUG")
        url = f"{DEXSCREENER_TOKEN_PAIRS_API}{token_address}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        
        log(f"Resposta da API para {token_address} - Status: {response.status_code}", "DEBUG")
        
        if not response.content:
            log(f"Resposta vazia para o token {token_address}", "ERROR")
            return None
            
        data = response.json()
        
        # Verificar estrutura esperada
        if isinstance(data, list):
            log(f"Resposta contém lista de pares para {token_address}", "DEBUG")
            return {"pairs": data}
        elif isinstance(data, dict) and "pairs" in data:
            log(f"Resposta no formato esperado para {token_address}", "DEBUG")
            return data
        elif isinstance(data, dict):
            log(f"Resposta é um dicionário sem chave 'pairs' - tratando como par único", "DEBUG")
            return {"pairs": [data]}
        else:
            log(f"Formato inesperado dos dados para {token_address}: {type(data)}", "ERROR")
            return None
            
    except requests.exceptions.RequestException as e:
        log(f"Erro na requisição para {token_address}: {str(e)}", "ERROR")
        return None
    except ValueError as e:
        log(f"Erro ao decodificar JSON para {token_address}: {str(e)}", "ERROR")
        return None
    except Exception as e:
        log(f"Erro inesperado ao acessar {token_address}: {str(e)}", "ERROR")
        return None

def get_main_pair(token_data):
    """Obtém o par principal dos dados do token com tratamento robusto."""
    if not isinstance(token_data, dict):
        log("Dados do token não são um dicionário", "ERROR")
        return None
        
    try:
        # Tenta obter pares de várias formas possíveis
        pairs = token_data.get("pairs", [])
        if not isinstance(pairs, list):
            if isinstance(token_data, list):
                pairs = token_data
            else:
                pairs = [token_data]
        
        if not pairs:
            log("Nenhum par encontrado nos dados do token", "WARNING")
            return None
            
        # Encontra o par com maior liquidez
        main_pair = None
        max_liquidity = 0
        
        for pair in pairs:
            try:
                if not isinstance(pair, dict):
                    continue
                    
                liquidity_data = pair.get("liquidity", {})
                if not isinstance(liquidity_data, dict):
                    liquidity_data = {}
                    
                liquidity = float(liquidity_data.get("usd", 0))
                
                if liquidity > max_liquidity:
                    main_pair = pair
                    max_liquidity = liquidity
                    
            except (TypeError, ValueError) as e:
                log(f"Erro ao processar par: {str(e)}", "DEBUG")
                continue
                
        if not main_pair and pairs:
            log("Usando primeiro par disponível (não foi possível calcular liquidez)", "WARNING")
            main_pair = pairs[0] if isinstance(pairs[0], dict) else None
                
        if not main_pair:
            log("Nenhum par válido encontrado", "WARNING")
            return None
            
        return main_pair
        
    except Exception as e:
        log(f"Erro ao obter par principal: {str(e)}", "ERROR")
        return None

def calculate_investment_risk(pair):
    """Calcula o risco de investimento conforme o modelo solicitado."""
    if not isinstance(pair, dict):
        return None
        
    try:
        liquidity = float(pair.get('liquidity', {}).get('usd', 0))
        volume_24h = float(pair.get('volume', {}).get('h24', 0))
        price_change_24h = float(pair.get('priceChange', {}).get('h24', 0))

        # Cálculo conforme o modelo solicitado
        risk_score = (liquidity / 10000) - (volume_24h / 100000) + (abs(price_change_24h) / 10)
        risk_percentage = min(100, max(0, risk_score * 10))  # Convertendo para porcentagem 0-100%
        
        return {
            'liquidity': liquidity,
            'volume_24h': volume_24h,
            'price_change_24h': price_change_24h,
            'risk_score': risk_score,
            'risk_percentage': risk_percentage
        }
    except Exception as e:
        log(f"Erro ao calcular risco: {str(e)}", "ERROR")
        return None

def generate_token_info(token_profile, token_data):
    """Gera as informações formatadas sobre o token no novo modelo."""
    if not isinstance(token_profile, dict) or not isinstance(token_data, dict):
        return "Informações do token inválidas", None
        
    token_address = token_profile.get("tokenAddress", "Desconhecido")
    links = token_profile.get("links", [])
    
    # Formata os links
    links_formatted = ""
    if isinstance(links, list):
        for link in links:
            if isinstance(link, dict):
                if link.get("type") == "twitter":
                    links_formatted += f"🐦 <a href='{link.get('url', '')}'>Twitter</a> | "
                elif link.get("type") == "telegram":
                    links_formatted += f"📢 <a href='{link.get('url', '')}'>Telegram</a> | "
                elif link.get("url"):
                    links_formatted += f"🌐 <a href='{link.get('url', '')}'>Site</a> | "
    
    # Obtém o par principal
    pair = get_main_pair(token_data)
    if not pair:
        return "Dados do par não disponíveis", None
    
    # Calcula risco
    risk_data = calculate_investment_risk(pair)
    if not risk_data:
        return "Erro ao calcular risco", None
    
    # Link para o gráfico de velas no GeckoTerminal
    gecko_link = f"https://www.geckoterminal.com/solana/pools/{token_address}"
    
    # Formata a mensagem conforme o modelo solicitado
    message = (
        f"<b>✅ Novo Token Detectado!</b>\n\n"
        f"<b>Liquidez:</b> {risk_data['liquidity']/1000:.1f}K\n"
        f"<b>Volume 24h:</b> {risk_data['volume_24h']/1000:.1f}K\n"
        f"<b>Mudança de Preço 24h:</b> {risk_data['price_change_24h']:.2f}%\n\n"
        f"<b>Cálculo de Risco:</b> ({risk_data['liquidity']:.2f} / 10,000) - {risk_data['volume_24h']:.2f} / 100,000) + (|{risk_data['price_change_24h']:.2f}| / 10) = {risk_data['risk_score']:.2f}\n"
        f"<b>Porcentagem de Risco:</b> {risk_data['risk_percentage']:.0f}%\n\n"
        f"<b>🔗 Links:</b> {links_formatted}\n"
        f"<b>📊 Gráfico:</b> <a href='{gecko_link}'>GeckoTerminal</a>\n"
        f"<b>🔍 DexScreener:</b> <a href='{token_profile.get('url', '')}'>Abrir</a>\n"
        f"<b>🆔 Address:</b> <code>{token_address}</code>"
    )
    
    return message, pair

def generate_plotly_graph(pair, token_name):
    """Gera um gráfico refinado usando Plotly com cores para valores positivos/negativos."""
    if not isinstance(pair, dict):
        log("Dados inválidos para gerar gráfico", "ERROR")
        return None
        
    try:
        time_frames = ["m5", "h1", "h6", "h24"]
        labels = ["5 min", "1 hora", "6 horas", "24 horas"]
        
        price_changes = []
        volumes = []
        
        for tf in time_frames:
            try:
                price_change = float(pair.get("priceChange", {}).get(tf, 0))
                volume = float(pair.get("volume", {}).get(tf, 0))
                price_changes.append(price_change)
                volumes.append(volume)
            except (TypeError, ValueError):
                price_changes.append(0)
                volumes.append(0)
                log(f"Erro ao processar dados para {tf}", "DEBUG")

        # Cores baseadas nos valores (verde para positivo, vermelho para negativo)
        bar_colors = ['#4CAF50' if pc >= 0 else '#F44336' for pc in price_changes]
        text_colors = ['white' for _ in price_changes]  # Cor do texto sempre branca

        fig = go.Figure()

        # Gráfico de barras para mudança de preço com cores condicionais
        fig.add_trace(
            go.Bar(
                x=labels,
                y=price_changes,
                name="Variação de Preço (%)",
                marker_color=bar_colors,
                text=[f"{val:.1f}%" for val in price_changes],
                textposition="outside",
                textfont=dict(color=text_colors),
                hoverinfo="y+name",
            )
        )

        # Gráfico de linha para volume
        fig.add_trace(
            go.Scatter(
                x=labels,
                y=volumes,
                name="Volume (USD)",
                mode="lines+markers",
                yaxis="y2",
                line=dict(color="#2196F3", width=3),
                marker=dict(size=10, color="#2196F3"),
                text=[f"${val/1000:.1f}K" for val in volumes],
                hoverinfo="y+name",
            )
        )

        fig.update_layout(
            title=dict(
                text=f"Performance: {token_name}",
                font=dict(size=18, color="white"),
                x=0.5,
            ),
            xaxis=dict(
                title="Intervalo de Tempo", 
                color="white",
                showgrid=False,
                linecolor="#444",
                mirror=True
            ),
            yaxis=dict(
                title="Variação de Preço (%)", 
                color="white",
                gridcolor="#444",
                zerolinecolor="#444",
            ),
            yaxis2=dict(
                title="Volume (USD)",
                overlaying="y",
                side="right",
                color="white",
                gridcolor="#444",
                zeroline=False
            ),
            paper_bgcolor="#1E1E2E",
            plot_bgcolor="#1E1E2E",
            font=dict(color="white"),
            legend=dict(
                orientation="h", 
                yanchor="bottom", 
                y=1.02, 
                xanchor="right", 
                x=1,
                font=dict(color="white")
            ),
            margin=dict(l=50, r=50, b=50, t=80, pad=4),
            hoverlabel=dict(
                bgcolor="#2E2E3E",
                font_size=12,
                font_color="white"
            ),
        )

        buffer = BytesIO()
        fig.write_image(buffer, format="png", scale=2)
        buffer.seek(0)
        return buffer
    except Exception as e:
        log(f"Erro ao gerar gráfico: {str(e)}", "ERROR")
        return None

def send_to_telegram(message, image_buffer=None):
    """Envia uma mensagem no Telegram com tratamento robusto de erros."""
    try:
        log("Preparando para enviar mensagem para o Telegram", "DEBUG")
        
        if not message or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            log("Configurações inválidas para envio", "ERROR")
            return False
        
        if image_buffer:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            files = {'photo': ('graph.png', image_buffer, 'image/png')}
            data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': message, 'parse_mode': 'HTML'}
            response = requests.post(url, files=files, data=data, timeout=15)
        else:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            data = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'HTML', 'disable_web_page_preview': True}
            response = requests.post(url, json=data, timeout=15)
        
        response.raise_for_status()
        return True
        
    except requests.exceptions.HTTPError as e:
        log(f"Erro HTTP: {e.response.status_code} - {e.response.text}", "ERROR")
    except requests.exceptions.RequestException as e:
        log(f"Erro de conexão: {str(e)}", "ERROR")
    except Exception as e:
        log(f"Erro inesperado: {str(e)}", "ERROR")
    
    return False

def is_pump_token(token_address):
    """Verifica se o token termina com 'pump' (case insensitive)."""
    if not isinstance(token_address, str):
        return False
    return token_address.lower().endswith('pump')

def process_new_tokens():
    """Processa e envia novos tokens."""
    log("Iniciando processo de busca por novos tokens", "INFO")
    token_profiles = fetch_token_profiles()
    
    if not token_profiles:
        log("Nenhum perfil de token encontrado", "WARNING")
        return False
    
    tokens_sent = 0
    for token_profile in token_profiles:
        if not isinstance(token_profile, dict):
            continue
            
        token_address = token_profile.get("tokenAddress")
        
        if not token_address or token_address in known_tokens or is_pump_token(token_address):
            continue
            
        token_data = fetch_token_details(token_address)
        if not token_data:
            continue
            
        pair = get_main_pair(token_data)
        if not pair:
            continue
            
        liquidity = float(pair.get("liquidity", {}).get("usd", 0))
        if liquidity < LIQUIDITY_THRESHOLD:
            continue
            
        message, pair = generate_token_info(token_profile, token_data)
        graph_buffer = generate_plotly_graph(pair, token_address)
        
        if send_to_telegram(message, graph_buffer):
            known_tokens.append(token_address)
            tokens_sent += 1
        
        time.sleep(1)
    
    log(f"Processamento concluído. Tokens enviados: {tokens_sent}", "INFO")
    return tokens_sent > 0

def main():
    log("Iniciando bot de monitoramento de tokens", "INFO")
    while True:
        try:
            process_new_tokens()
            time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            log("Bot interrompido manualmente", "INFO")
            break
        except Exception as e:
            log(f"Erro no loop principal: {str(e)}", "ERROR")
            time.sleep(10)

if __name__ == "__main__":
    main()