package dev.plexzy.prisongens.enchants.listener;

import dev.plexzy.prisongens.PrisonGens;
import dev.plexzy.prisongens.enchants.CustomEnchant;
import dev.plexzy.prisongens.enchants.menu.PickaxeMenu;
import dev.plexzy.prisongens.mine.MineRegion;
import org.bukkit.GameMode;
import org.bukkit.block.Block;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.block.Action;
import org.bukkit.event.block.BlockBreakEvent;
import org.bukkit.event.player.PlayerInteractEvent;
import org.bukkit.inventory.ItemStack;

import java.util.Map;
import java.util.UUID;

public class MineListener implements Listener {

    private final PrisonGens plugin;
    // Evita recursión infinita cuando los enchants rompen bloques artificialmente
    private final ThreadLocal<Boolean> isEnchantMining = ThreadLocal.withInitial(() -> false);

    public MineListener(PrisonGens plugin) {
        this.plugin = plugin;
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onBlockBreak(BlockBreakEvent event) {
        Player player = event.getPlayer();
        if (player.getGameMode() == GameMode.CREATIVE) return;

        Block block = event.getBlock();
        UUID islandId = plugin.getIslandManager().getIslandId(player);
        
        // Verificar si el bloque está dentro de la mina de la isla
        if (islandId != null) {
            MineRegion mine = plugin.getMineManager().getMine(islandId);
            if (mine != null && mine.contains(block.getLocation())) {
                
                // Si la ruptura fue causada por un encantamiento, no volver a disparar enchants
                if (isEnchantMining.get()) return;

                ItemStack pickaxe = player.getInventory().getItemInMainHand();
                if (pickaxe.getType().toString().endsWith("PICKAXE")) {
                    
                    Map<CustomEnchant, Integer> enchants = plugin.getEnchantManager().getActiveEnchants(pickaxe);
                    
                    if (!enchants.isEmpty()) {
                        isEnchantMining.set(true); // Bloquear recursión
                        try {
                            for (Map.Entry<CustomEnchant, Integer> entry : enchants.entrySet()) {
                                // Aquí llamamos a la lógica individual de cada encantamiento
                                entry.getKey().onMine(player, block, entry.getValue(), pickaxe);
                            }
                        } finally {
                            isEnchantMining.set(false); // Liberar
                        }
                    }
                }
            }
        }
    }

    @EventHandler
    public void onPickaxeRightClick(PlayerInteractEvent event) {
        if (event.getAction() == Action.RIGHT_CLICK_AIR || event.getAction() == Action.RIGHT_CLICK_BLOCK) {
            Player player = event.getPlayer();
            if (player.isSneaking()) {
                ItemStack item = player.getInventory().getItemInMainHand();
                if (item.getType().toString().endsWith("PICKAXE")) {
                    // Abrir menú de mejoras
                    new PickaxeMenu(plugin).open(player, item);
                }
            }
        }
    }
}
