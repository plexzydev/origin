package com.servermc.prisongens.listeners;

import com.servermc.prisongens.PrisonGens;
import com.servermc.prisongens.managers.EconomyManager;
import com.servermc.prisongens.managers.PickaxeManager;
import org.bukkit.GameMode;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.World;
import org.bukkit.block.Block;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.block.BlockBreakEvent;
import org.bukkit.event.block.BlockPlaceEvent;
import org.bukkit.inventory.ItemStack;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;

public class MineListener implements Listener {

    private final PrisonGens plugin;

    public MineListener(PrisonGens plugin) {
        this.plugin = plugin;
    }

    @EventHandler
    public void onBlockBreak(BlockBreakEvent event) {
        Player player = event.getPlayer();
        if (player.getGameMode() == GameMode.CREATIVE) return;

        Block block = event.getBlock();

        // Protect structural blocks
        if (block.getType() == Material.BEDROCK || block.getType() == Material.OAK_FENCE ||
            block.getType() == Material.POLISHED_DEEPSLATE || block.getType() == Material.POLISHED_DEEPSLATE_WALL ||
            block.getType() == Material.LANTERN || block.getType() == Material.SEA_LANTERN ||
            block.getType() == Material.GRASS_BLOCK || block.getType() == Material.DIRT ||
            block.getType() == Material.STONE_BRICK_SLAB) {
            event.setCancelled(true);
            return;
        }

        if (plugin.getIslandManager().getIsland(player) == null) {
            event.setCancelled(true);
            return;
        }

        event.setDropItems(false);
        event.setExpToDrop(0);

        int[] stats = plugin.getPickaxeManager().getStats(player);
        int fortune = stats[PickaxeManager.PrisonEnchant.FORTUNE.ordinal()];
        int jackhammer = stats[PickaxeManager.PrisonEnchant.JACKHAMMER.ordinal()];
        int explosive = stats[PickaxeManager.PrisonEnchant.EXPLOSIVE.ordinal()];
        int laser = stats[PickaxeManager.PrisonEnchant.LASER.ordinal()];
        int tokenGreed = stats[PickaxeManager.PrisonEnchant.TOKENGREED.ordinal()];
        int autoSell = stats[PickaxeManager.PrisonEnchant.AUTOSELL.ordinal()];

        // Collect blocks to break
        List<Block> blocksToBreak = new ArrayList<>();
        blocksToBreak.add(block);

        // Jackhammer: break entire layer
        if (jackhammer > 0 && Math.random() < 0.05 * jackhammer) {
            int y = block.getY();
            for (int x = -16; x <= 16; x++) {
                for (int z = -16; z <= 16; z++) {
                    Block b = block.getWorld().getBlockAt(block.getX() + x, y, block.getZ() + z);
                    if (isMineable(b.getType()) && !blocksToBreak.contains(b)) {
                        blocksToBreak.add(b);
                    }
                }
            }
        }

        // Explosive: 3x3x3 area
        if (explosive > 0) {
            int radius = 1 + (explosive / 10);
            for (int x = -radius; x <= radius; x++) {
                for (int y = -radius; y <= radius; y++) {
                    for (int z = -radius; z <= radius; z++) {
                        Block b = block.getRelative(x, y, z);
                        if (isMineable(b.getType()) && !blocksToBreak.contains(b)) {
                            blocksToBreak.add(b);
                        }
                    }
                }
            }
        }

        // Laser: line of blocks in facing direction
        if (laser > 0) {
            org.bukkit.util.Vector dir = player.getLocation().getDirection();
            for (int d = 1; d <= 3 + laser; d++) {
                Location loc = block.getLocation().clone().add(dir.clone().multiply(d));
                Block b = loc.getBlock();
                if (isMineable(b.getType()) && !blocksToBreak.contains(b)) {
                    blocksToBreak.add(b);
                }
            }
        }

        // Process all blocks
        double totalMoney = 0;
        int totalTokens = 0;
        int totalItems = 0;

        for (Block b : blocksToBreak) {
            Material dropType = getDropMaterial(b.getType());
            int amount = 1 + (fortune > 0 ? (int)(Math.random() * (fortune + 1)) : 0);
            totalItems += amount;

            if (autoSell > 0) {
                totalMoney += getPrice(dropType) * amount;
            } else {
                ItemStack drop = new ItemStack(dropType, amount);
                player.getInventory().addItem(drop);
            }

            // Tokens
            double tokenChance = 0.08 + (tokenGreed * 0.02);
            if (Math.random() < tokenChance) {
                totalTokens += 1 + (int)(Math.random() * (2 + tokenGreed));
            }

            if (b != block) b.setType(Material.AIR);
        }

        if (autoSell > 0 && totalMoney > 0) {
            plugin.getEconomyManager().addBalance(player, EconomyManager.MONEY, totalMoney);
        }
        if (totalTokens > 0) {
            plugin.getEconomyManager().addBalance(player, EconomyManager.TOKENS, totalTokens);
        }
    }

    @EventHandler
    public void onBlockPlace(BlockPlaceEvent event) {
        if (event.getPlayer().getGameMode() != GameMode.CREATIVE) {
            event.setCancelled(true);
        }
    }

    private boolean isMineable(Material mat) {
        return mat != Material.AIR && mat != Material.BEDROCK && mat != Material.OAK_FENCE &&
               mat != Material.GRASS_BLOCK && mat != Material.DIRT && mat != Material.STONE &&
               mat != Material.COBBLESTONE && mat != Material.POLISHED_DEEPSLATE &&
               mat != Material.LANTERN && mat != Material.SEA_LANTERN &&
               mat != Material.STONE_BRICK_SLAB || isOre(mat);
    }

    private boolean isOre(Material mat) {
        return mat == Material.COBBLESTONE || mat == Material.IRON_ORE || mat == Material.GOLD_ORE ||
               mat == Material.DIAMOND_ORE || mat == Material.EMERALD_ORE || mat == Material.ANCIENT_DEBRIS;
    }

    private Material getDropMaterial(Material blockType) {
        return switch (blockType) {
            case COBBLESTONE -> Material.COBBLESTONE;
            case IRON_ORE, DEEPSLATE_IRON_ORE -> Material.RAW_IRON;
            case GOLD_ORE, DEEPSLATE_GOLD_ORE -> Material.RAW_GOLD;
            case DIAMOND_ORE, DEEPSLATE_DIAMOND_ORE -> Material.DIAMOND;
            case EMERALD_ORE, DEEPSLATE_EMERALD_ORE -> Material.EMERALD;
            case ANCIENT_DEBRIS -> Material.NETHERITE_SCRAP;
            default -> blockType;
        };
    }

    private double getPrice(Material material) {
        return switch (material) {
            case COBBLESTONE -> 1.0;
            case RAW_IRON -> 5.0;
            case RAW_GOLD -> 15.0;
            case DIAMOND -> 50.0;
            case EMERALD -> 150.0;
            case NETHERITE_SCRAP -> 500.0;
            default -> 0.0;
        };
    }
}
