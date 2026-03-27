gamerule players_sleeping_percentage 0

# Carpet
carpet setDefault optimizedTNT true
carpet optimizedTNTHighPriority true
carpet optimizedFastEntityMovement true
carpet commandPlayer true

# LuckPerms
lp group default permission set tabtps.tps true
lp group default permission set tabtps.ping true
lp group default permission set tabtps.defaultdisplay true
lp group default permission set tabtps.toggle true
lp group default permission set tabtps.toggle.tab true
lp group default permission set tabtps.toggle.actionbar true
lp group default permission set tabtps.toggle.bossbar true

lp creategroup carpet_trusted
lp group carpet_trusted permission set carpet.commands.player true
lp group carpet_trusted parent add default
