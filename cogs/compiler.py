from discord.ext import commands
import discord
import requests
import json

class Compiler(commands.Cog):
	def __init__(self, bot):
		self.bot = bot

	@commands.command()
	async def compile(self, ctx, language=None, *, code=None):
		"""
		listRequest = requests.get("https://wandbox.org/api/list.json")
		compilerList = json.loads(listRequest.text)
		
		for i in compilerList:
			if i["language"] == language:
				compiler = i["name"]
				print(compiler)
		"""
		compilers = {
			"python":"cpython-3.8.0",
			"c":"gcc-head-c",
			"javascript":"nodejs-head",
			"typescript":"typescript-3.5.1",
			"c#":"dotnetcore-head",
			"bash": "bash",
			"vim-script": "vim-head",
			"cpp": "gcc-head",
			"swift": "swift-5.0.1",
			"php": "php-head",
			"coffeescript": "coffeescript-head",
			"go": "go-head",
			"java": "openjdk-head",
			"ruby": "ruby-head",
			"rust": "rust-head",
			"sql": "sqlite-head",
			"perl": "perl-head",
			"lua": "lua-5.3.4"
			}
		if not language:
			await ctx.send(f"```json\n{json.dumps(compilers, indent=4)}```")
		if not code:
			await ctx.send("No code found")
			return
		try:
			compiler = compilers[language]
		except KeyError:
			await ctx.send("Language not found")
			return
		body = {
			"compiler": compiler,
			"code": code,
			"save": True
			}
		head = {
			"Content-Type":"application/json"
			}
		async with ctx.typing():
			r = requests.post("https://wandbox.org/api/compile.json", headers=head, data=json.dumps(body))
			try:
				response = json.loads(r.text)
				#await ctx.send(f"```json\n{json.dumps(response, indent=4)}```")
				print(f"```json\n{json.dumps(response, indent=4)}```")
			except json.decoder.JSONDecodeError:
				await ctx.send(f"```json\n{r.text}```")

			try:
				embed=discord.Embed(title="Compiled code")
				embed.add_field(name="Output", value=f'```{response["program_message"]}```', inline=False)
				embed.add_field(name="Exit code", value=response["status"], inline=True)
				embed.add_field(name="Link", value=f"[Permalink]({response['url']})", inline=True)
				await ctx.send(embed=embed)
			except KeyError:
				await ctx.send(f"```json\n{json.dumps(response, indent=4)}```")

def setup(bot):
	bot.add_cog(Compiler(bot))