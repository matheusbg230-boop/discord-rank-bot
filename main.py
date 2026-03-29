import discord
from discord.ext import commands, tasks
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
from threading import Thread
import shelve
db = shelve.open('/tmp/botdb', writeback=True)
import json
import os

# ========== CONFIGURAÇÃO ==========
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "SEU_TOKEN_AQUI")
CHANNEL_ID = 1484027524462805173
SERVER_ID = 1482927871038197991
ADMIN_ID = 856354431943966721  # Só você (Futurano) pode remover membros

# Membros fixos iniciais
MEMBROS_FIXOS = {
    "Amandasegredinhos_BOT": {"nome": "Kaue 🚀", "discord_id": 1482928441123672294},
    "Julinha_Safadinha_BOT": {"nome": "Victor 💎", "discord_id": 1083588317548916838},
    "thaisconteudinhos_bot": {"nome": "Futurano ✨", "discord_id": 856354431943966721},
}

MEDALHAS = ["🥇", "🥈", "🥉"]

# ========== MEMBROS ==========


def get_membros():
    membros = dict(MEMBROS_FIXOS)
    # Remove os fixos que foram removidos pelo admin
    removidos = []
    raw_rem = db.get("membros_fixos_removidos")
    if raw_rem:
        try:
            removidos = json.loads(raw_rem)
        except Exception:
            pass
    for bot_name in removidos:
        membros.pop(bot_name, None)
    # Adiciona os cadastrados
    dados = db.get("membros_cadastrados")
    if dados:
        try:
            membros.update(json.loads(dados))
        except Exception:
            pass
    return membros


def salvar_membro(bot_name, nome_display, discord_id):
    dados = {}
    raw = db.get("membros_cadastrados")
    if raw:
        try:
            dados = json.loads(raw)
        except Exception:
            pass
    dados[bot_name] = {"nome": nome_display, "discord_id": int(discord_id)}
    db["membros_cadastrados"] = json.dumps(dados)


def remover_membro(bot_name):
    # Se for membro fixo, salva numa lista de removidos
    if bot_name in MEMBROS_FIXOS:
        removidos = []
        raw = db.get("membros_fixos_removidos")
        if raw:
            try:
                removidos = json.loads(raw)
            except Exception:
                pass
        if bot_name not in removidos:
            removidos.append(bot_name)
        db["membros_fixos_removidos"] = json.dumps(removidos)
        return True, "ok"
    # Se for membro cadastrado, remove normalmente
    dados = {}
    raw = db.get("membros_cadastrados")
    if raw:
        try:
            dados = json.loads(raw)
        except Exception:
            pass
    if bot_name not in dados:
        return False, "Membro não encontrado!"
    del dados[bot_name]
    db["membros_cadastrados"] = json.dumps(dados)
    return True, "ok"


# ========== BANCO DE DADOS ==========


def _proximo_idx():
    idx = db.get("next_idx") or 0
    db["next_idx"] = idx + 1
    return idx


def adicionar_venda(bot_name, valor, cliente):
    idx = _proximo_idx()
    chave = f"venda_{idx}"
    db[chave] = json.dumps(
        {
            "bot_name": bot_name,
            "valor": float(valor),
            "cliente": cliente,
            "data": datetime.now().isoformat(),
        }
    )
    print(f"✅ Venda salva [{chave}]: {bot_name} R$ {valor:.2f}")


def get_vendas_periodo(horas=None):
    membros = get_membros()
    totais = {bot: 0.0 for bot in membros}
    limite = (datetime.now() - timedelta(hours=horas)) if horas else None

    for chave in db.keys():
        if not chave.startswith("venda_"):
            continue
        try:
            v = json.loads(db[chave])
            if v["bot_name"] not in membros:
                continue
            if limite:
                if datetime.fromisoformat(v["data"]) < limite:
                    continue
            totais[v["bot_name"]] += v["valor"]
        except Exception:
            continue

    membros_info = get_membros()
    ranking = [
        (membros_info[bot]["nome"], membros_info[bot]["discord_id"], total)
        for bot, total in totais.items()
    ]
    ranking.sort(key=lambda x: x[2], reverse=True)
    return ranking


def formatar_ranking(ranking):
    texto = ""
    for i, (nome, discord_id, total) in enumerate(ranking):
        medalha = MEDALHAS[i] if i < 3 else f"**{i + 1}º**"
        mencao = f" (<@{discord_id}>)" if discord_id else ""
        texto += f"{medalha} {nome}{mencao}: R$ {total:,.2f}\n"
    return texto.strip()


# ========== EMBEDS ==========


def build_embed(periodo="hoje"):
    hoje = get_vendas_periodo(horas=24)
    semana = get_vendas_periodo(horas=168)
    mes = get_vendas_periodo(horas=720)
    total_dia = sum(t for _, _, t in hoje)

    if periodo == "hoje":
        titulo_periodo = "📅 HOJE"
        ranking_texto = formatar_ranking(hoje)
        cor = discord.Color.gold()
    elif periodo == "semana":
        titulo_periodo = "📊 ESSA SEMANA"
        ranking_texto = formatar_ranking(semana)
        cor = discord.Color.blue()
    else:
        titulo_periodo = "📈 ESTE MÊS"
        ranking_texto = formatar_ranking(mes)
        cor = discord.Color.green()

    embed = discord.Embed(
        title="🏆 RANKING DE FATURAMENTO DOS MEMBROS DA NOVA ERA",
        description=f"Ranking atualizado de vendas dos membros da Nova Era\n💰 **Faturamento hoje:** R$ {total_dia:,.2f}",
        color=cor,
        timestamp=datetime.now(),
    )
    embed.add_field(name=titulo_periodo, value=ranking_texto, inline=False)
    embed.set_footer(text="Atualizado automaticamente a cada 5 minutos")
    return embed


# ========== MODAL DE CADASTRO ==========


class CadastroModal(discord.ui.Modal, title="📋 Participar do Ranking"):
    nome_display = discord.ui.TextInput(
        label="Seu nome no ranking",
        placeholder="Ex: João 💰",
        min_length=2,
        max_length=30,
    )
    bot_telegram = discord.ui.TextInput(
        label="Nome do seu bot do Telegram",
        placeholder="Ex: MeuBot_BOT  (exatamente como está no Telegram)",
        min_length=3,
        max_length=60,
    )

    async def on_submit(self, interaction: discord.Interaction):
        membros = get_membros()
        bot_name = self.bot_telegram.value.strip()
        nome = self.nome_display.value.strip()
        user_id = interaction.user.id

        if bot_name in membros:
            await interaction.response.send_message(
                f"❌ O bot `{bot_name}` já está cadastrado no ranking!", ephemeral=True
            )
            return

        salvar_membro(bot_name, nome, user_id)
        print(f"✅ Novo membro: {nome} | Bot: {bot_name} | Discord: {user_id}")

        await interaction.response.send_message(
            f"✅ **{nome}** foi adicionado ao ranking!\n"
            f"🤖 Bot: `{bot_name}`\n"
            f"As suas vendas já serão contabilizadas automaticamente!",
            ephemeral=True,
        )


# ========== SELECT PARA REMOVER MEMBRO ==========


class RemoverSelect(discord.ui.Select):
    def __init__(self):
        membros = get_membros()
        opcoes = []
        for bot_name, info in membros.items():
            opcoes.append(
                discord.SelectOption(
                    label=info["nome"],
                    value=bot_name,
                    description=f"Bot: {bot_name[:50]}",
                )
            )

        if not opcoes:
            opcoes = [
                discord.SelectOption(label="Nenhum membro no ranking", value="none")
            ]

        super().__init__(
            placeholder="Selecione o membro para remover...",
            options=opcoes[:25],  # Discord permite max 25 opções
            custom_id="select_remover",
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message(
                "❌ Você não tem permissão!", ephemeral=True
            )
            return

        bot_name = self.values[0]
        if bot_name == "none":
            await interaction.response.send_message(
                "❌ Não há membros para remover!", ephemeral=True
            )
            return

        membros = get_membros()
        nome = membros.get(bot_name, {}).get("nome", bot_name)
        sucesso, msg = remover_membro(bot_name)

        if sucesso:
            await interaction.response.send_message(
                f"✅ **{nome}** foi removido do ranking!", ephemeral=True
            )
        else:
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True)


class RemoverView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(RemoverSelect())


# ========== BOTÕES PRINCIPAIS ==========


class RankingView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="📅 Hoje", style=discord.ButtonStyle.primary, custom_id="btn_hoje"
    )
    async def btn_hoje(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        embed = build_embed(periodo="hoje")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(
        label="📊 Semanal", style=discord.ButtonStyle.secondary, custom_id="btn_semanal"
    )
    async def btn_semanal(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        embed = build_embed(periodo="semana")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(
        label="📈 Mensal", style=discord.ButtonStyle.secondary, custom_id="btn_mensal"
    )
    async def btn_mensal(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        embed = build_embed(periodo="mes")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(
        label="🙋 Participar do Ranking",
        style=discord.ButtonStyle.success,
        custom_id="btn_participar",
    )
    async def btn_participar(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_modal(CadastroModal())

    @discord.ui.button(
        label="🗑️ Remover Membro",
        style=discord.ButtonStyle.danger,
        custom_id="btn_remover",
    )
    async def btn_remover(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message(
                "❌ Apenas o administrador pode remover membros!", ephemeral=True
            )
            return

        membros = get_membros()
        if not membros:
            await interaction.response.send_message(
                "❌ Não há membros no ranking para remover!", ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Selecione o membro que deseja remover:", view=RemoverView(), ephemeral=True
        )


# ========== DISCORD BOT ==========
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

MESSAGE_ID_KEY = "ranking_message_id"


@bot.event
async def on_ready():
    print(f"✅ Bot online como {bot.user}")
    bot.add_view(RankingView())
    if not atualizar_ranking.is_running():
        atualizar_ranking.start()


@tasks.loop(minutes=5)
async def atualizar_ranking():
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print("❌ Canal não encontrado!")
        return

    embed = build_embed(periodo="hoje")
    view = RankingView()

    msg_id = db.get(MESSAGE_ID_KEY)
    if msg_id:
        try:
            msg = await channel.fetch_message(int(msg_id))
            await msg.edit(embed=embed, view=view)
            print("✏️ Ranking atualizado!")
            return
        except Exception:
            pass

    msg = await channel.send(embed=embed, view=view)
    db[MESSAGE_ID_KEY] = str(msg.id)
    print("📨 Nova mensagem de ranking enviada!")


@bot.command(name="ranking")
async def cmd_ranking(ctx):
    await ctx.message.delete()
    channel = bot.get_channel(CHANNEL_ID)
    embed = build_embed(periodo="hoje")
    view = RankingView()
    msg_id = db.get(MESSAGE_ID_KEY)
    if msg_id:
        try:
            msg = await channel.fetch_message(int(msg_id))
            await msg.edit(embed=embed, view=view)
            return
        except Exception:
            pass
    msg = await channel.send(embed=embed, view=view)
    db[MESSAGE_ID_KEY] = str(msg.id)


# ========== FLASK ==========
app = Flask(__name__)


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json or {}
        bot_name = data.get("bot_name") or data.get("profile_name", "")
        valor = float(data.get("valor") or data.get("amount", 0))
        cliente = data.get("cliente") or data.get("customer_name", "Anônimo")

        if bot_name and valor > 0:
            adicionar_venda(bot_name, valor, cliente)

        return jsonify({"status": "success"}), 200
    except Exception as e:
        print(f"❌ Erro no webhook: {e}")
        return jsonify({"status": "success"}), 200

@app.route("/")
def health():
    return "✅ Bot Online!", 200


def run_flask():
    app.run(host="0.0.0.0", port=8080)


if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    bot.run(DISCORD_TOKEN)
