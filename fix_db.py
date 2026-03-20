import os
import re

def fix_files():
    for root, _, files in os.walk('src'):
        for file in files:
            if not file.endswith('.py'): continue
            path = os.path.join(root, file)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            new_content = content
            
            if file == 'db.py' and root.endswith('modules'):
                new_content = new_content.replace('async def get_user_data(db, user_id: int) -> dict:', 'async def get_user_data(db, guild_id: int, user_id: int) -> dict:')
                new_content = new_content.replace('key = str(user_id)', 'key = f"{guild_id}_{user_id}"')
                new_content = new_content.replace('db.users.find_one({"_id": user_id})', 'db.users.find_one({"guild_id": guild_id, "user_id": user_id})')
                new_content = new_content.replace('async def invalidate_user_data(user_id: int):', 'async def invalidate_user_data(guild_id: int, user_id: int):')
                new_content = new_content.replace('await user_data_cache.invalidate(str(user_id))', 'await user_data_cache.invalidate(f"{guild_id}_{user_id}")')
            
            elif file == 'user.py' and 'repositories' in root:
                new_content = new_content.replace('user = await get_user_data(db, user_id)', 'user = await get_user_data(db, guild_id, user_id)')
                new_content = new_content.replace('await invalidate_user_data(user_id)', 'await invalidate_user_data(guild_id, user_id)')
            else:
                new_content = re.sub(r'get_user_data\(db,\s*interaction\.user\.id\)', r'get_user_data(db, interaction.guild.id, interaction.user.id)', new_content)
                new_content = re.sub(r'invalidate_user_data\(interaction\.user\.id\)', r'invalidate_user_data(interaction.guild.id, interaction.user.id)', new_content)
                
                new_content = re.sub(r'get_user_data\(db,\s*self\.user_id\)', r'get_user_data(db, interaction.guild.id, self.user_id)', new_content)
                new_content = re.sub(r'invalidate_user_data\(self\.user_id\)', r'invalidate_user_data(interaction.guild.id, self.user_id)', new_content)

                new_content = re.sub(r'invalidate_user_data\(self\.owner_id\)', r'invalidate_user_data(interaction.guild.id, self.owner_id)', new_content)
                
                new_content = re.sub(r'invalidate_user_data\(user_id\)', r'invalidate_user_data(interaction.guild.id, user_id)', new_content)
                new_content = re.sub(r'invalidate_user_data\(target_id\)', r'invalidate_user_data(interaction.guild.id, target_id)', new_content)
                new_content = re.sub(r'invalidate_user_data\(target_user_id\)', r'invalidate_user_data(interaction.guild.id, target_user_id)', new_content)

            if new_content != content:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"Fixed {path}")

if __name__ == '__main__':
    fix_files()
